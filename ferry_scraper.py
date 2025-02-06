from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from bs4 import BeautifulSoup
import time
import csv
import random
from datetime import datetime, timedelta
import re
import urllib.parse
import itertools
import json  # To help parse JSON arrays from JS

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/110.0.5481.100 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/109.0.5414.87 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/108.0.5359.100 Safari/537.36"
]

# Update this path to where your chromedriver executable is located.
CHROME_DRIVER_PATH = r"C:\Users\USER\chromedriver\chromedriver-win64\chromedriver.exe"

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

def get_locations(driver):
    """
    Extract locations from the JavaScript variable 'fromCityList'
    on the search page. This version uses json.loads() to preserve spaces.
    """
    try:
        driver.get("https://www.phanganferries.com/search")
        time.sleep(2)  # allow page to load
        page_source = driver.page_source

        # Look for: var fromCityList = ["Koh Phangan", "Krabi", ...];
        match = re.search(r'var\s+fromCityList\s*=\s*(\[[^\]]*\]);', page_source)
        if match:
            locations_json = match.group(1)
            try:
                locations = json.loads(locations_json)
                print(f"Found locations: {locations}")
                return locations
            except Exception as json_err:
                print(f"JSON parsing error: {json_err}")
                # Fallback: remove brackets and quotes manually
                locations = locations_json.strip("[]").split(",")
                locations = [loc.strip(' "\'') for loc in locations if loc.strip()]
                print(f"Found locations (fallback): {locations}")
                return locations
        else:
            print("Error: 'fromCityList' variable not found in page source.")
            return []
    except Exception as e:
        print(f"Error getting locations: {e}")
        return []

def extract_schedule_data(html, search_date=None):
    """Extract schedule data including adult and child prices."""
    soup = BeautifulSoup(html, "html.parser")
    schedules = []

    schedule_items = soup.find_all("div", class_="tableout")
    print(f"Found {len(schedule_items)} schedule items.")

    for i, item in enumerate(schedule_items):
        print(f"\nProcessing schedule item {i+1}...")
        try:
            # --- Operator extraction ---
            operator_div = item.find("div", class_="wione")
            if operator_div:
                operator_img = operator_div.find("img")
                if operator_img:
                    logo_url = operator_img.get('src', '')
                    # Extract operator name from the logo URL (using a simple heuristic)
                    operator_name = logo_url.split('/')[-1].split('_')[-1].split('.')[0]
                    operator_name = f"Operator_{operator_name[:8]}" if operator_name else "Unknown"
                else:
                    operator_name = "No Logo"
            else:
                operator_name = "N/A"
            
            # --- Basic info extraction from form-to div ---
            form_to_div = item.find("div", class_="form-to")
            if not form_to_div:
                print(f"    Error: No form-to div found in item {i+1}")
                continue

            # Extract departure details
            from_div = form_to_div.find("div", class_="witwo")
            from_location = from_div.find("p", class_="location").text.strip() if from_div else "N/A"
            departure_time = from_div.find("h5", class_="time").text.strip() if from_div else "N/A"
            
            # Extract arrival details
            to_div = form_to_div.find("div", class_="withree")
            to_location = to_div.find("p", class_="location").text.strip() if to_div else "N/A"
            arrival_time = to_div.find("h5", class_="time").text.strip() if to_div else "N/A"

            # --- Price extraction from wifive div ---
            price_adult = "N/A"
            price_child = "N/A"
            price_div = item.find("div", class_="wifive")
            if price_div:
                spans = price_div.find_all("span")
                if len(spans) > 0:
                    price_adult = spans[0].text.strip()
                    print(f"    Found adult price: {price_adult}")
                if len(spans) > 1:
                    price_child = spans[1].text.strip()
                    print(f"    Found child price: {price_child}")

            # --- Vehicle type detection ---
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
            print(f"Error processing schedule item {i+1}: {str(e)}")
            continue

    return schedules

def construct_search_url(base_url, from_location, to_location, journey_date, adult_no=1, children_no=0, children_ages=None):
    """
    Constructs the search URL using the provided parameters.
    This version URL-encodes the parameters so that, for example,
    "Koh Phangan" becomes "Koh+Phangan" and "Hua Hin" becomes "Hua+Hin",
    and it includes empty order_type and order_by parameters.
    """
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

def scrape_single_url(url, driver, search_date):
    """Scrapes data from a single URL and returns the schedule data."""
    all_schedules = []
    print(f"\nAccessing URL: {url}")
    driver.get(url)
    time.sleep(2)  # wait for page to load; adjust as needed

    schedules = extract_schedule_data(driver.page_source, search_date)
    all_schedules.extend(schedules)
    return all_schedules

def save_to_csv(schedules, filename="ferry_schedules.csv"):
    """Save schedules to a CSV file."""
    if not schedules:
        print("No schedules to save.")
        return

    fields = ['search_date', 'from_location', 'to_location', 'departure_time',
              'arrival_time', 'price_adult', 'price_child', 
              'operator', 'vessel']

    with open(filename, mode='w', newline='', encoding='utf-8') as file:
        writer = csv.DictWriter(file, fieldnames=fields)
        writer.writeheader()
        writer.writerows(schedules)
    print(f"Schedules saved to {filename}")

def main():
    base_search_url = "https://www.phanganferries.com/search"
    # Define passenger counts: 1 adult and 1 child aged 3.
    adult_no = 1
    children_no = 1
    children_ages = [3]

    # Set the start date as February 8, 2025.
    start_date = datetime(2025, 2, 8)
    num_days = 7  # Run for 7 consecutive days

    print("Starting dynamic ferry schedule scraping for 7 days of data...")

    driver = setup_driver()
    try:
        # Get the list of locations (for both 'from' and 'to')
        locations = get_locations(driver)
        if not locations:
            print("No locations found. Exiting.")
            return

        all_schedules = []
        # Loop through each day
        for day in range(num_days):
            current_date = start_date + timedelta(days=day)
            # Format the journey date as "DD MMM, YYYY" (e.g., "08 Feb, 2025")
            journey_date = current_date.strftime("%d %b, %Y")
            print(f"\nScraping data for date: {journey_date}")

            # Loop through all location combinations (skip same-from-to pairs)
            for from_loc, to_loc in itertools.product(locations, repeat=2):
                if from_loc == to_loc:
                    continue  # skip identical locations
                url = construct_search_url(base_search_url, from_loc, to_loc, journey_date,
                                            adult_no=adult_no, children_no=children_no,
                                            children_ages=children_ages)
                print(f"\nScraping route: {from_loc} -> {to_loc} on {journey_date}")
                schedules = scrape_single_url(url, driver, journey_date)
                if schedules:
                    all_schedules.extend(schedules)
                else:
                    print("    No schedules found for this route.")
                # Sleep a random amount to mimic human behavior and reduce load on the server.
                time.sleep(random.uniform(2, 4))
        
        if all_schedules:
            current_date_str = datetime.now().strftime("%Y-%m-%d")
            csv_filename = f"ferry_schedules_{current_date_str}.csv"
            save_to_csv(all_schedules, csv_filename)
            print(f"\nSuccessfully scraped {len(all_schedules)} schedule entries.")
        else:
            print("No schedules were found for any route on any day.")

    except Exception as e:
        print(f"An error occurred: {e}")
    finally:
        driver.quit()

    print("Scraping completed.")

if __name__ == "__main__":
    main()
