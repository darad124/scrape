import os
# Suppress TensorFlow Lite logs
os.environ["TF_CPP_MIN_LOG_LEVEL"] = "3"

import json
import re
import csv
import time
import random
import threading
import urllib.parse
import itertools
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# -------------------- Configuration --------------------
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/110.0.5481.100 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/109.0.5414.87 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/108.0.5359.100 Safari/537.36"
]

CHROME_DRIVER_PATH = r"C:\Users\USER\chromedriver\chromedriver-win64\chromedriver.exe"  # Use your path
CSV_FILENAME = "ferry_schedules_final_final.csv"  # Changed filename
VALID_ROUTES_FILE = "valid_routes.json"
MAX_WORKERS = 4

# Use a reentrant lock
csv_lock = threading.RLock()
thread_local = threading.local()

# -------------------- Functions --------------------

def setup_driver():
    """Set up and return a configured Chrome WebDriver."""
    chrome_options = Options()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument(f"user-agent={random.choice(USER_AGENTS)}")
    service = Service(executable_path=CHROME_DRIVER_PATH)
    return webdriver.Chrome(service=service, options=chrome_options)

def get_thread_driver():
    """Get or create a thread-local WebDriver instance."""
    if not hasattr(thread_local, "driver"):
        thread_local.driver = setup_driver()
    return thread_local.driver

def get_locations(driver):
    """Extract locations."""
    try:
        driver.get("https://www.phanganferries.com/search")
        time.sleep(2)
        page_source = driver.page_source
        match = re.search(r'var\s+fromCityList\s*=\s*(\[[^\]]*\]);', page_source)
        if match:
            locations_json = match.group(1)
            try:
                return json.loads(locations_json)
            except Exception:
                locations = locations_json.strip("[]").split(",")
                return [loc.strip(' "\'') for loc in locations if loc.strip()]
        return []
    except Exception as e:
        print(f"Error getting locations: {e}")
        return []

def extract_route_details(route_div):
    """Extract route details (CORRECTED AND FINAL VERSION)."""
    route_id_elem = route_div.find("ul", class_="nav-tabs")
    route_id = route_id_elem.get("route_id", "N/A") if route_id_elem else "N/A"
    route_details = {"route_id": route_id, "segments": []}

    route_info_detailed = route_div.find("div", class_="route-detail-left")
    if not route_info_detailed:  return route_details

    ul_element = route_info_detailed.find("ul", class_="route-info-detailed")
    if not ul_element: return route_details

    list_items = ul_element.find_all("li", recursive=False)
    if not list_items: return route_details

    current_segment = None

    for i, li in enumerate(list_items):
        h5 = li.find("h5")
        h4 = li.find("h4")
        trip_location = li.find("p", class_="trip-location")
        trip_time = li.find("p", class_="trip-time")

        if h5 and h4:  # "FROM" segment - Start a NEW segment
            current_segment = {
                "from": {
                    "location": h4.get_text(strip=True) if h4 else "N/A",
                    "address": trip_location.contents[0].strip() if trip_location and trip_location.contents else "N/A",
                    "departure_time": trip_time.find("b").get_text(strip=True) if trip_time and trip_time.find("b") else "N/A",
                    "check_in_note": trip_time.find("span").get_text(strip=True) if trip_time and trip_time.find("span") else "N/A",
                },
                "to": {},  # 'to' is filled in LATER
                "transport": [],
                "duration": "N/A",
                "layover": "0 Hr. 0 Min.",
            }
            route_details["segments"].append(current_segment)

            # Get transport for the FROM segment
            transport_icons_div = li.find("ul", class_="mobtrip-info")
            if transport_icons_div:
                for img in transport_icons_div.find_all("img"):
                    src = img.get("src")
                    if src == "/img/icon_ship.png":
                        current_segment["transport"].append("Ferry")
                    elif src == "/img/icon_bus.png":
                        current_segment["transport"].append("Bus")

        elif h4:  # Intermediate Stop (Update PREVIOUS segment's "to")
            if current_segment:
                current_segment["to"] = {
                    "location": h4.get_text(strip=True) if h4 else "N/A",
                    "address": trip_location.contents[0].strip() if trip_location and trip_location.contents else "N/A",
                    "arrival_time": trip_time.find("b").get_text(strip=True) if trip_time and trip_time.find("b") else "N/A",
                }
            # --- Handle 'mobtrip-infoone' (Additional Transport and potential new segment) ---
            transport_icons_div = li.find("ul", class_="mobtrip-infoone")
            if transport_icons_div:
                # Check if we need to create a NEW segment (if mobtrip-infoone exists)
                if len(route_details["segments"]) >= 1:
                    new_segment = {
                        "from": current_segment["to"],  # New 'from' is previous 'to'
                        "to": {},  # 'to' will be filled in the *next* iteration (or at the very end)
                        "transport": [],
                        "duration": "N/A",
                        "layover": "0 Hr. 0 Min.",  # Default
                    }
                    route_details["segments"].append(new_segment)
                    current_segment = new_segment

                for img in transport_icons_div.find_all("img"):
                    src = img.get("src")
                    if src == "/img/icon_ship.png":
                        current_segment["transport"].append("Ferry")
                    elif src == "/img/icon_bus.png":
                        current_segment["transport"].append("Bus")

                # Handle "same bus"
                if trip_location and (same_bus_span := trip_location.find("span")):
                    if "same bus" in same_bus_span.get_text(strip=True).lower():
                        current_segment["transport"].append("Bus")

    # --- Fill in "to" for the LAST segment ---
    if current_segment:
        last_li = list_items[-1]  # Get the very last <li>
        last_h4 = last_li.find("h4")
        last_trip_location = last_li.find("p", class_="trip-location")
        last_trip_time = last_li.find("p", class_="trip-time")

        current_segment["to"] = {  # Update the *last* segment's "to"
            "location": last_h4.get_text(strip=True) if last_h4 else "N/A",
            "address": last_trip_location.contents[0].strip() if last_trip_location and last_trip_location.contents else "N/A",
            "arrival_time": last_trip_time.find("b").get_text(strip=True) if last_trip_time and last_trip_time.find("b") else "N/A",
        }

    # --- Extract Durations and Layovers (from route-detail-right) ---
    transport_right_div = route_div.find("div", class_="route-detail-right")
    if transport_right_div:
        h5_elements = transport_right_div.find_all("h5")
        segment_index = 0

        for element in h5_elements:
            if segment_index < len(route_details["segments"]):  # prevent list out of bound
                text = element.get_text(strip=True)
                if "Layover" in text:
                    route_details["segments"][segment_index]["layover"] = text
                else:
                    route_details["segments"][segment_index]["duration"] = text
                segment_index += 1

    return route_details

def extract_information(info_div):
    """Extract and return information as string"""
    information_text = ""
    if info_div:
        search_info_detail_div = info_div.find("div", class_="search-info-detail")
        if search_info_detail_div:
            # Get all text content, preserving paragraph structure
            paragraphs = search_info_detail_div.find_all("p")
            information_text = "\n".join(p.get_text(strip=True) for p in paragraphs)
    return information_text

def extract_schedule_data(html, search_date=None):
    """Extract schedule data from HTML."""
    soup = BeautifulSoup(html, "html.parser")
    schedules = []

    for i, item in enumerate(soup.find_all("div", class_="tableout")):
        try:
            # --- Basic extractions ---
            operator_div = item.find("div", class_="wione")
            operator_name = operator_div.find("img").get('alt', 'N/A') if operator_div and operator_div.find("img") else "N/A"

            form_to_div = item.find("div", class_="form-to")
            if not form_to_div: continue
            from_div = form_to_div.find("div", class_="witwo")
            from_location = from_div.find("p", class_="location").text.strip() if from_div else "N/A"
            departure_time = from_div.find("h5", class_="time").text.strip() if from_div else "N/A"
            to_div = form_to_div.find("div", class_="withree")
            to_location = to_div.find("p", class_="location").text.strip() if to_div else "N/A"
            arrival_time = to_div.find("h5", class_="time").text.strip() if to_div else "N/A"

            # --- Price extraction (Simplified) ---
            price_adult = "N/A"
            price_child = "N/A"
            price_div = item.find("div", class_="wifive")
            if price_div:
                spans = price_div.find_all("span")
                if spans:
                    price_adult = spans[0].text.strip() if len(spans) > 0 else "N/A"
                    price_child = spans[1].text.strip() if len(spans) > 1 else "N/A"

            # --- Determine vessel type ---
            vehicle_types = []
            transport_div = form_to_div.find("div", class_="transport-icon")
            if transport_div:
                if transport_div.find("img", src="/img/icon_ship.png"): vehicle_types.append("Ferry")
                if transport_div.find("img", src="/img/icon_bus.png"): vehicle_types.append("Bus")
            vessel = " + ".join(vehicle_types) if vehicle_types else "N/A"

            # --- Find and extract detailed trip information ---
            trip_detail_main = item.find_next_sibling("div", class_="trip-detail-main")
            route_details = {}
            information = {}
            cancellation_policy = "N/A"
            from_location_address = "N/A"
            to_location_address = "N/A"

            if trip_detail_main:
                # --- Route Details ---
                route_tab = trip_detail_main.find("div", id=lambda x: x and x.startswith("trip_route-"))
                if route_tab:
                    route_details = extract_route_details(route_tab)  # Use the CORRECTED function
                    # Extract addresses from route details
                    if route_details and route_details["segments"]:
                        from_location_address = route_details["segments"][0]["from"]["address"]
                        to_location_address = route_details["segments"][-1]["to"]["address"]

                # --- Information ---
                info_tab = trip_detail_main.find("div", id=lambda x: x and x.startswith("trip_info-"))
                if info_tab:
                    information = extract_information(info_tab)

                # --- Cancellation Policy ---
                cancel_tab = trip_detail_main.find("div", id=lambda x: x and x.startswith("trip_cancel-"))
                if cancel_tab:
                    cancel_policy_div = cancel_tab.find("div", class_="cancel-policy")
                    if cancel_policy_div:
                        cancellation_policy = "\n".join(p.get_text(strip=True) for p in cancel_policy_div.find_all("p"))

            # --- Create the schedule dictionary ---
            schedule = {
                'search_date': search_date,
                'from_location': from_location,
                'to_location': to_location,
                'from_location_address': from_location_address,
                'to_location_address': to_location_address,
                'departure_time': departure_time,
                'arrival_time': arrival_time,
                'price_adult': price_adult,
                'price_child': price_child,
                'operator': operator_name,
                'vessel': vessel,
                'cancellation_policy': cancellation_policy,
                'route_details': json.dumps(route_details),  # Store as JSON string
                'information': information
            }
            schedules.append(schedule)

        except Exception as e:
            print(f"Error processing schedule item {i+1}: {e}")
            continue

    return schedules

def extract_coordinates(html):
    """Extract ferry route coordinates from HTML using BeautifulSoup.
    Returns separate fields for from_lat, from_lon, to_lat, and to_lon."""
    soup = BeautifulSoup(html, "html.parser")
    coordinates = []
    # For each schedule container (tableout div)
    for tableout_div in soup.find_all("div", class_="tableout"):
        trip_detail = tableout_div.find_next_sibling("div", class_="trip-detail-main")
        from_lat = "N/A"
        from_lon = "N/A"
        to_lat = "N/A"
        to_lon = "N/A"
        if trip_detail:
            # Find the map tab with id starting with "trip_map-"
            map_tab = trip_detail.find("div", id=lambda x: x and x.startswith("trip_map-"))
            if map_tab:
                # Find the search-map div within the map tab
                search_map_div = map_tab.find("div", class_="search-map")
                if search_map_div:
                    try:
                        from_lat = search_map_div.get("from_lat", "N/A")
                        from_lon = search_map_div.get("from_long", "N/A")
                        to_lat = search_map_div.get("to_lat", "N/A")
                        to_lon = search_map_div.get("to_long", "N/A")
                    except Exception as e:
                        print(f"Error extracting coordinates: {e}")
        coordinates.append({
            "from_lat": from_lat,
            "from_lon": from_lon,
            "to_lat": to_lat,
            "to_lon": to_lon
        })
    return coordinates

def construct_search_url(base_url, from_location, to_location, journey_date, adult_no=1, children_no=0, children_ages=None):
    """Constructs the search URL."""
    from_location_encoded = urllib.parse.quote_plus(from_location)
    to_location_encoded = urllib.parse.quote_plus(to_location)
    journey_date_encoded = urllib.parse.quote_plus(journey_date)
    url = (f"{base_url}?order_type=&order_by=&loc_from={from_location_encoded}"
           f"&loc_to={to_location_encoded}"
           f"&journey_date={journey_date_encoded}"
           f"&adult_no={adult_no}"
           f"&children_no={children_no}")
    if children_no > 0 and children_ages:
        for i, age in enumerate(children_ages, start=1):
            url += f"&children_age%5B{i}%5D={age}"
    return url

def append_to_csv(schedules, filename):
    """Append schedule data to CSV."""
    if not schedules:
        return
    fields = ['search_date', 'from_location', 'to_location', 'from_location_address', 'to_location_address',
              'departure_time', 'arrival_time', 'price_adult', 'price_child', 'operator', 'vessel',
              'cancellation_policy', 'route_details', 'information',
              'from_lat', 'from_lon', 'to_lat', 'to_lon']
    with csv_lock:
        with open(filename, mode='a', newline='', encoding='utf-8') as file:
            writer = csv.DictWriter(file, fieldnames=fields)
            if file.tell() == 0:
                writer.writeheader()  # Write header only if file is empty
            for schedule in schedules:
                writer.writerow(schedule)

def scrape_route_for_date(args):
    from_loc, to_loc, journey_date = args
    driver = get_thread_driver()
    try:
        url = construct_search_url("https://www.phanganferries.com/search",
                                     from_loc, to_loc, journey_date,
                                     adult_no=1, children_no=1, children_ages=[3])
        print(f"Scraping route: {from_loc} -> {to_loc} for {journey_date}")
        driver.get(url)
        WebDriverWait(driver, 30).until(
            EC.presence_of_all_elements_located((By.CLASS_NAME, "tableout"))
        )
        schedules = extract_schedule_data(driver.page_source, journey_date)
        
        # Extract and integrate ferry route coordinates into separate columns
        coordinates = extract_coordinates(driver.page_source)
        if coordinates:
            for schedule, coord_data in zip(schedules, coordinates):
                schedule['from_lat'] = coord_data['from_lat']
                schedule['from_lon'] = coord_data['from_lon']
                schedule['to_lat'] = coord_data['to_lat']
                schedule['to_lon'] = coord_data['to_lon']
                
        if schedules:
            append_to_csv(schedules, CSV_FILENAME)
            print(f"Found {len(schedules)} schedules for {from_loc} -> {to_loc}")
            return len(schedules)
        return 0
    except Exception as e:
        print(f"Error scraping route {from_loc} -> {to_loc}: {e}")
        return 0

def validate_route(from_loc, to_loc, journey_date):
    """Check if a route exists."""
    driver = get_thread_driver()
    url = construct_search_url("https://www.phanganferries.com/search", from_loc, to_loc, journey_date, adult_no=1)
    try:
        driver.get(url)
        WebDriverWait(driver, 5).until(
            EC.presence_of_element_located((By.TAG_NAME, "body"))
        )
        return len(driver.find_elements(By.CLASS_NAME, "tableout")) > 0
    except Exception:
        return False

def discover_valid_routes(locations, sample_date):
    """Build valid routes map."""
    valid_routes = {}
    total_combinations = len(locations) * (len(locations) - 1)
    print(f"Discovering valid routes from {total_combinations} possible combinations...")

    route_combinations = [(from_loc, to_loc) for from_loc, to_loc in itertools.product(locations, repeat=2) if from_loc != to_loc]

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        future_to_route = {executor.submit(validate_route, from_loc, to_loc, sample_date): (from_loc, to_loc)
                           for from_loc, to_loc in route_combinations}
        for future in future_to_route:
            try:
                from_loc, to_loc = future_to_route[future]
                is_valid = future.result()
                if is_valid:
                    valid_routes.setdefault(from_loc, []).append(to_loc)
                    print(f"Valid route found: {from_loc} -> {to_loc}")
            except Exception as e:
                print(f"Error processing route validation: {e}")

    with open(VALID_ROUTES_FILE, 'w', encoding='utf-8') as f:
        json.dump(valid_routes, f, indent=2)
    return valid_routes

def load_or_discover_valid_routes(locations, sample_date):
    """Load or discover valid routes."""
    if os.path.exists(VALID_ROUTES_FILE):
        with open(VALID_ROUTES_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return discover_valid_routes(locations, sample_date)

# -------------------- Main Script --------------------

def main():
    base_search_url = "https://www.phanganferries.com/search"
    # Starting from 12th February for 7 days
    start_date = datetime(2025, 2, 12)
    num_days = 7

    print("Starting ferry schedule scraping...")

    # Write CSV header if the file does not exist or is empty
    if not os.path.exists(CSV_FILENAME) or os.stat(CSV_FILENAME).st_size == 0:
        csv_fields = ['search_date', 'from_location', 'to_location', 'from_location_address', 'to_location_address',
                      'departure_time', 'arrival_time', 'price_adult', 'price_child', 'operator', 'vessel',
                      'cancellation_policy', 'route_details', 'information',
                      'from_lat', 'from_lon', 'to_lat', 'to_lon']
        with open(CSV_FILENAME, mode='w', newline='', encoding='utf-8') as file:
            writer = csv.DictWriter(file, fieldnames=csv_fields)
            writer.writeheader()

    driver = setup_driver()
    try:
        locations = get_locations(driver)
        if not locations:
            print("No locations found. Exiting.")
            return
    finally:
        driver.quit()

    sample_date = start_date.strftime("%d %b, %Y")
    valid_routes = load_or_discover_valid_routes(locations, sample_date)

    scraping_tasks = []
    for day_index in range(num_days):
        current_date = start_date + timedelta(days=day_index)
        journey_date = current_date.strftime("%d %b, %Y")
        for from_loc, to_loc_list in valid_routes.items():
            for to_loc in to_loc_list:
                scraping_tasks.append((from_loc, to_loc, journey_date))

    total_schedules = 0
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = [executor.submit(scrape_route_for_date, task) for task in scraping_tasks]
        for future in futures:
            try:
                total_schedules += future.result()
            except Exception as e:
                print(f"Error processing task: {e}")

    print(f"\nScraping completed. Total schedules found: {total_schedules}")
    print("Exiting script.")

if __name__ == "__main__":
    main()
