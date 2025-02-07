import os
# Suppress TensorFlow Lite logs (set before any TensorFlow or related libraries are imported)
os.environ["TF_CPP_MIN_LOG_LEVEL"] = "3"

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
from bs4 import BeautifulSoup
import time
import csv
import random
from datetime import datetime, timedelta
import re
import urllib.parse
import itertools
import json
import threading
from concurrent.futures import ThreadPoolExecutor

# -------------------- Configuration --------------------
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/110.0.5481.100 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/109.0.5414.87 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/108.0.5359.100 Safari/537.36"
]

CHROME_DRIVER_PATH = r"C:\Users\USER\chromedriver\chromedriver-win64\chromedriver.exe"
CSV_FILENAME = "ferry_schedules_progress.csv"
CHECKPOINT_FILE = "checkpoint.json"
MAX_WORKERS = 4
VALID_ROUTES_FILE = "valid_routes.json"

# Use a reentrant lock to avoid deadlocks in nested locking
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
        chrome_options = Options()
        chrome_options.add_argument("--headless")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument(f"user-agent={random.choice(USER_AGENTS)}")
        service = Service(executable_path=CHROME_DRIVER_PATH)
        thread_local.driver = webdriver.Chrome(service=service, options=chrome_options)
    return thread_local.driver

def get_locations(driver):
    """Extract locations from the JavaScript variable 'fromCityList'."""
    try:
        driver.get("https://www.phanganferries.com/search")
        time.sleep(2)
        page_source = driver.page_source
        match = re.search(r'var\s+fromCityList\s*=\s*(\[[^\]]*\]);', page_source)
        if match:
            locations_json = match.group(1)
            try:
                locations = json.loads(locations_json)
                print(f"Found locations: {locations}")
                return locations
            except Exception as json_err:
                print(f"JSON parsing error: {json_err}")
                locations = locations_json.strip("[]").split(",")
                locations = [loc.strip(' "\'') for loc in locations if loc.strip()]
                print(f"Found locations (fallback): {locations}")
                return locations
        else:
            print("Error: 'fromCityList' variable not found.")
            return []
    except Exception as e:
        print(f"Error getting locations: {e}")
        return []

def extract_schedule_data(html, search_date=None):
    """Extract schedule data from the HTML using BeautifulSoup."""
    soup = BeautifulSoup(html, "html.parser")
    schedules = []

    for i, item in enumerate(soup.find_all("div", class_="tableout")):
        print(f"\nProcessing schedule item {i+1}...")
        try:
            # Extract operator information
            operator_name = "N/A"
            operator_div = item.find("div", class_="wione")
            if operator_div and (operator_img := operator_div.find("img")):
                logo_url = operator_img.get('src', '')
                operator_name = f"Operator_{logo_url.split('/')[-1].split('_')[-1].split('.')[0][:8]}" if logo_url else "No Logo"

            # Extract departure and arrival info
            form_to_div = item.find("div", class_="form-to")
            if not form_to_div:
                print(f"    Error: No form-to div found in item {i+1}")
                continue
            from_div = form_to_div.find("div", class_="witwo")
            from_location = from_div.find("p", class_="location").text.strip() if from_div else "N/A"
            departure_time = from_div.find("h5", class_="time").text.strip() if from_div else "N/A"
            to_div = form_to_div.find("div", class_="withree")
            to_location = to_div.find("p", class_="location").text.strip() if to_div else "N/A"
            arrival_time = to_div.find("h5", class_="time").text.strip() if to_div else "N/A"

            # Price extraction
            price_adult = "N/A"
            price_child = "N/A"
            price_div = item.find("div", class_="wifive")
            if price_div:
                print(f"    Price div HTML: {price_div}")
                spans = price_div.find_all("span")
                if spans:
                    if len(spans) > 0:
                        price_adult = spans[0].text.strip()
                        print(f"    Found adult price (simple method): {price_adult}")
                    if len(spans) > 1:
                        price_child = spans[1].text.strip()
                        print(f"    Found child price (simple method): {price_child}")

                # Fallback methods if simple extraction fails
                if price_adult == "N/A":
                    print("    Simple price extraction failed, trying robust methods.")
                    tour_price_div = price_div.find("div", class_="tour-price")
                    if tour_price_div:
                        print("    Found tour-price div")
                        for p in tour_price_div.find_all("p"):
                            p_text = p.get_text(strip=True)
                            print(f"    Processing paragraph text: {p_text}")
                            span = p.find("span")
                            if span:
                                if "Adult" in p_text or "adult" in p_text:
                                    price_adult = span.get_text(strip=True)
                                    print(f"    Found adult price (method 1): {price_adult}")
                                elif "Child" in p_text or "child" in p_text:
                                    price_child = span.get_text(strip=True)
                                    print(f"    Found child price (method 1): {price_child}")
                        if price_adult == "N/A" or price_child == "N/A":
                            print("    Trying method 2 for price extraction")
                            for span in price_div.find_all("span"):
                                parent_text = span.parent.get_text(strip=True)
                                span_text = span.get_text(strip=True)
                                print(f"    Analyzing span: {span_text} with parent text: {parent_text}")
                                if "Adult" in parent_text or "adult" in parent_text:
                                    if price_adult == "N/A":
                                        price_adult = span_text
                                        print(f"    Found adult price (method 2): {price_adult}")
                                elif "Child" in parent_text or "child" in parent_text:
                                    if price_child == "N/A":
                                        price_child = span_text
                                        print(f"    Found child price (method 2): {price_child}")
                        if price_adult == "N/A" or price_child == "N/A":
                            print("    Trying method 3 for price extraction")
                            full_text = price_div.get_text(strip=True)
                            print(f"    Full price div text: {full_text}")
                            price_matches = re.findall(r'THB\s*(\d+(?:,\d+)?)', full_text)
                            if len(price_matches) >= 2:
                                if price_adult == "N/A":
                                    price_adult = f"THB {price_matches[0]}"
                                    print(f"    Found adult price (method 3): {price_adult}")
                                if price_child == "N/A":
                                    price_child = f"THB {price_matches[1]}"
                                    print(f"    Found child price (method 3): {price_child}")

            # Determine vessel type
            vehicle_types = []
            transport_div = form_to_div.find("div", class_="transport-icon")
            if transport_div:
                if transport_div.find("img", src="/img/icon_ship.png"):
                    vehicle_types.append("Ferry")
                if transport_div.find("img", src="/img/icon_bus.png"):
                    vehicle_types.append("Bus")
            vessel = " + ".join(vehicle_types) if vehicle_types else "N/A"

            schedule = {
                'search_date': search_date,
                'from_location': from_location,
                'to_location': to_location,
                'departure_time': departure_time,
                'arrival_time': arrival_time,
                'price_adult': price_adult,
                'price_child': price_child,
                'operator': operator_name,
                'vessel': vessel
            }
            schedules.append(schedule)
            print(f"    Successfully extracted schedule {i+1}")
            for key, value in schedule.items():
                print(f"    {key}: {value}")

        except Exception as e:
            print(f"Error processing schedule item {i+1}: {e}")
            continue

    return schedules

def construct_search_url(base_url, from_location, to_location, journey_date, adult_no=1, children_no=0, children_ages=None):
    """Constructs the search URL with parameters."""
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
    """Append schedule data to the CSV file."""
    if not schedules:
        return
    fields = ['search_date', 'from_location', 'to_location', 'departure_time',
              'arrival_time', 'price_adult', 'price_child', 'operator', 'vessel']
    # Locking is done here using the RLock
    with csv_lock:
        with open(filename, mode='a', newline='', encoding='utf-8') as file:
            writer = csv.DictWriter(file, fieldnames=fields)
            for schedule in schedules:
                writer.writerow(schedule)

def scrape_route_for_date(args):
    from_loc, to_loc, journey_date = args
    driver = get_thread_driver()  # Reuse thread-local driver
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
        if schedules:
            append_to_csv(schedules, CSV_FILENAME)
            print(f"Found {len(schedules)} schedules for {from_loc} -> {to_loc}")
            return len(schedules)
        return 0
    except Exception as e:
        print(f"Error scraping route {from_loc} -> {to_loc}: {e}")
        return 0
    # Removed driver.quit() here

def load_checkpoint():
    """Load checkpoint data if it exists."""
    if os.path.exists(CHECKPOINT_FILE):
        try:
            with open(CHECKPOINT_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"Error reading checkpoint: {e}")
    return {"day_index": 0, "pair_index": 0}

def update_checkpoint(day_index, pair_index):
    """Write checkpoint data to file."""
    cp = {"day_index": day_index, "pair_index": pair_index}
    try:
        with open(CHECKPOINT_FILE, "w", encoding="utf-8") as f:
            json.dump(cp, f)
    except Exception as e:
        print(f"Error updating checkpoint: {e}")

def clear_checkpoint():
    """Remove the checkpoint file."""
    if os.path.exists(CHECKPOINT_FILE):
        os.remove(CHECKPOINT_FILE)

def validate_route(from_loc, to_loc, journey_date):
    """Check if a route exists by making a quick request."""
    driver = get_thread_driver()
    url = construct_search_url("https://www.phanganferries.com/search", from_loc, to_loc, journey_date, adult_no=1)
    try:
        driver.get(url)
        WebDriverWait(driver, 5).until(
            EC.presence_of_element_located((By.TAG_NAME, "body"))
        )
        return len(driver.find_elements(By.CLASS_NAME, "tableout")) > 0
    except Exception as e:
        print(f"Error validating route {from_loc} -> {to_loc}: {e}")
        return False

def discover_valid_routes(locations, sample_date):
    """Build a map of valid routes."""
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
    """Load valid routes from file or discover them."""
    if os.path.exists(VALID_ROUTES_FILE):
        with open(VALID_ROUTES_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return discover_valid_routes(locations, sample_date)

# -------------------- Main Script --------------------

def main():
    base_search_url = "https://www.phanganferries.com/search"
    start_date = datetime(2025, 2, 8)
    num_days = 7

    print("Starting optimized ferry schedule scraping...")
    csv_fields = ['search_date', 'from_location', 'to_location', 'departure_time',
                  'arrival_time', 'price_adult', 'price_child', 'operator', 'vessel']
    # Write CSV header if the file does not exist
    if not os.path.exists(CSV_FILENAME):
        with open(CSV_FILENAME, mode='w', newline='', encoding='utf-8') as file:
            writer = csv.DictWriter(file, fieldnames=csv_fields)
            writer.writeheader()

    # Use a single driver instance for initial location discovery
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

    # Build scraping tasks for each valid route on each day
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
    clear_checkpoint()
    print("Exiting script.")

if __name__ == "__main__":
    main()
