from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from bs4 import BeautifulSoup
import time
import csv
import random
from datetime import datetime, timedelta
import re

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/110.0.5481.100 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/109.0.5414.87 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/108.0.5359.100 Safari/537.36"
]

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
    """Extracts locations from the 'fromCityList' JavaScript variable."""
    try:
        driver.get("https://www.phanganferries.com/search")
        page_source = driver.page_source
        match = re.search(r'var fromCityList = (\[.*?\]);', page_source)
        if match:
            locations_str = match.group(1)
            locations_str = locations_str.replace('"', '').replace(" ", "")
            locations = locations_str[1:-1].split(",")
            locations = [loc for loc in locations if loc]
            return locations
        else:
            print("Error: fromCityList variable not found in page source.")
            return []

    except Exception as e:
        print(f"Error getting locations: {e}")
        return []

def extract_schedule_data(html, search_date=None):
    """Extract schedule data with corrected price extraction logic."""
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
                    # Extract operator name from the logo URL
                    logo_url = operator_img.get('src', '')
                    # Get the filename without extension
                    operator_name = logo_url.split('/')[-1].split('_')[-1].split('.')[0]
                    if operator_name:
                        operator_name = f"Operator_{operator_name[:8]}"  # Use first 8 chars of ID
                    else:
                        operator_name = "Unknown"
                else:
                    operator_name = "No Logo"
            else:
                operator_name = "N/A"
            
            # --- Basic info extraction from form-to div ---
            form_to_div = item.find("div", class_="form-to")
            if not form_to_div:
                print(f"    Error: No form-to div found in item {i+1}")
                continue

            # Location and time extraction
            from_div = form_to_div.find("div", class_="witwo")
            from_location = from_div.find("p", class_="location").text.strip() if from_div else "N/A"
            departure_time = from_div.find("h5", class_="time").text.strip() if from_div else "N/A"
            
            to_div = form_to_div.find("div", class_="withree")
            to_location = to_div.find("p", class_="location").text.strip() if to_div else "N/A"
            arrival_time = to_div.find("h5", class_="time").text.strip() if to_div else "N/A"

            # --- Price extraction from wifive div (outside form-to) ---
            price_adult = "N/A"
            price_div = item.find("div", class_="wifive")
            if price_div:
                price_span = price_div.find("span")
                if price_span:
                    price_adult = price_span.text.strip()
                    print(f"    Found price: {price_adult}")

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
                'from_location': from_location,
                'to_location': to_location,
                'departure_time': departure_time,
                'arrival_time': arrival_time,
                'price_adult': price_adult,
                'price_child': "N/A",
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

def construct_search_url(base_url, from_location, to_location, journey_date_str):
    """Constructs the search URL with pre-filled parameters."""
    from_location_encoded = from_location.replace(" ", "+")
    to_location_encoded = to_location.replace(" ", "+")
    url = f"{base_url}?loc_from={from_location_encoded}&loc_to={to_location_encoded}&journey_date={journey_date_str}&adult_no=1&children_no=0"
    return url

def scrape_single_url(url, driver):
    """Scrapes data from a single, provided URL."""
    all_schedules = []
    print(f"Accessing URL: {url}")
    driver.get(url)
    time.sleep(2)

    schedules = extract_schedule_data(driver.page_source)
    all_schedules.extend(schedules)
    return all_schedules

def save_to_csv(schedules, filename="ferry_schedules.csv"):
    """Save schedules to CSV."""
    if not schedules:
        print("No schedules to save.")
        return

    fields = ['from_location', 'to_location', 'departure_time',
              'arrival_time', 'price_adult', 'price_child', 
              'operator', 'vessel']

    with open(filename, mode='w', newline='', encoding='utf-8') as file:
        writer = csv.DictWriter(file, fieldnames=fields)
        writer.writeheader()
        writer.writerows(schedules)
    print(f"Schedules saved to {filename}")

def main():
    base_search_url = "https://www.phanganferries.com/search"
    # --- HARDCODED URL FOR TESTING ---
    test_url = "https://www.phanganferries.com/search?order_type=&order_by=&loc_from=Koh+Phangan&loc_to=Krabi+Ao+Nang&journey_date=08+Feb%2C+2025&adult_no=1&children_no=0"

    print("Starting ferry schedule scraping for a single URL...")

    driver = setup_driver()
    try:
        schedules = scrape_single_url(test_url, driver)
        if schedules:
            current_date_str = datetime.now().strftime("%Y-%m-%d")
            save_to_csv(schedules, f"ferry_schedules_test_{current_date_str}.csv")
            print(f"Successfully scraped {len(schedules)} schedule entries.")
        else:
            print("No schedules were found.")
    except Exception as e:
        print(f"An error occurred: {e}")
    finally:
        driver.quit()

    print("Scraping completed.")

if __name__ == "__main__":
    main()