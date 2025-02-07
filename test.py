import requests
from bs4 import BeautifulSoup
import json
import re
from urllib.parse import quote_plus

def construct_search_url(base_url, from_location, to_location, journey_date, adult_no=1, children_no=0, children_ages=None):
    """Constructs the search URL."""
    from_location_encoded = quote_plus(from_location)
    to_location_encoded = quote_plus(to_location)
    journey_date_encoded = quote_plus(journey_date)
    url = (f"{base_url}?order_type=&order_by=&loc_from={from_location_encoded}"
           f"&loc_to={to_location_encoded}"
           f"&journey_date={journey_date_encoded}"
           f"&adult_no={adult_no}"
           f"&children_no={children_no}")
    if children_no > 0 and children_ages:
        for i, age in enumerate(children_ages, start=1):
            url += f"&children_age%5B{i}%5D={age}"
    return url

def extract_route_details_test(route_div):
    """Extract route details (TEST VERSION) - Final, Corrected Version."""
    print("-" * 20, "EXTRACTING ROUTE DETAILS", "-" * 20)
    print(route_div.prettify())
    print("-" * 60)

    # --- 1. Get Route ID (CORRECTLY) ---
    route_id_elem = route_div.find("ul", class_="nav-tabs")
    route_id = route_id_elem.get("route_id", "N/A") if route_id_elem else "N/A"
    route_details = {"route_id": route_id, "segments": []}

    # --- 2. Find the main route information ---
    route_info_detailed = route_div.find("div", class_="route-detail-left")
    if not route_info_detailed:
        print("route-detail-left not found")
        return route_details

    ul_element = route_info_detailed.find("ul", class_="route-info-detailed")
    if not ul_element:
        print("No <ul> with class 'route-info-detailed' found")
        return route_details

    list_items = ul_element.find_all("li", recursive=False)
    if not list_items:
        print("No li elements found")
        return route_details

    # --- 3. Iterate through <li> elements (Main Loop) ---
    current_segment = None

    for i, li in enumerate(list_items):
        print(f"Processing li element {i+1}:")
        print(li.prettify())

        h5 = li.find("h5")
        h4 = li.find("h4")
        trip_location = li.find("p", class_="trip-location")
        trip_time = li.find("p", class_="trip-time")

        if h5 and h4:  # --- 3a. "FROM" segment (Start a NEW segment) ---
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

        elif h4:  # --- 3b. Intermediate Stop (Update PREVIOUS segment's "to") ---
            if current_segment:
                current_segment["to"] = {
                    "location": h4.get_text(strip=True) if h4 else "N/A",
                    "address": trip_location.contents[0].strip() if trip_location and trip_location.contents else "N/A",
                    "arrival_time": trip_time.find("b").get_text(strip=True) if trip_time and trip_time.find("b") else "N/A",
                }
            # --- 3c. Handle 'mobtrip-infoone' (Additional Transport and potential new segment) ---

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

    # --- 4. Fill in "to" for the LAST segment ---
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


    # --- 5. Extract Durations and Layovers (from route-detail-right) ---
    transport_right_div = route_div.find("div", class_="route-detail-right")
    if transport_right_div:
        print("Found route-detail-right")
        print(transport_right_div.prettify())

        h5_elements = transport_right_div.find_all("h5")
        segment_index = 0

        for element in h5_elements:
             if segment_index < len(route_details["segments"]): #prevent list out of bound
                text = element.get_text(strip=True)
                if "Layover" in text:
                    route_details["segments"][segment_index]["layover"] = text
                else:
                    route_details["segments"][segment_index]["duration"] = text
                segment_index += 1

    print("-" * 20, "FINISHED EXTRACTION", "-" * 20)
    return route_details
def scrape_single_route(from_location, to_location, journey_date):
    """Scrapes a single route and prints detailed output."""
    base_url = "https://www.phanganferries.com/search"
    url = construct_search_url(base_url, from_location, to_location, journey_date)
    print(f"Requesting URL: {url}")

    try:
        response = requests.get(url, timeout=10)  # Use requests for simplicity
        response.raise_for_status()  # Raise HTTPError for bad responses (4xx or 5xx)
    except requests.exceptions.RequestException as e:
        print(f"Request failed: {e}")
        return

    soup = BeautifulSoup(response.text, "html.parser")

    # Find the relevant div containing schedule data
    schedule_items = soup.find_all("div", class_="tableout")

    if not schedule_items:
        print("No schedule items found.")
        return

    for i, item in enumerate(schedule_items):
        print(f"\nProcessing schedule item {i+1}:")

        # Find the route details div
        trip_detail_main = item.find_next_sibling("div", class_="trip-detail-main")
        if not trip_detail_main:
            print("  No trip-detail-main found for this item.")
            continue

        route_tab = trip_detail_main.find("div", id=lambda x: x and x.startswith("trip_route-"))
        if not route_tab:
            print("  No trip_route tab found.")
            continue

        # Extract and print route details
        route_details = extract_route_details_test(route_tab)
        print(f"  Extracted Route Details: {json.dumps(route_details, indent=2)}")

if __name__ == "__main__":
    # Example usage: Scrape ONE route for ONE date
    from_location = "Koh Tao"      # Replace with your desired from location
    to_location = "Bangkok"         # Replace with your desired to location
    journey_date = "08 Feb, 2025"   # Replace with your desired date

    scrape_single_route(from_location, to_location, journey_date)
