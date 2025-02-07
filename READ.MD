
# Ferry Schedule Scraper

This project is a Python web scraper that uses Selenium and BeautifulSoup to extract ferry schedule data from the [Phangan Ferries website](https://www.phanganferries.com/search). The script gathers information such as departure and arrival times, operator details, and pricing, then saves the results to a CSV file.

> **Note:** This scraper uses threading to speed up the scraping process. Make sure you have a compatible version of Google Chrome and its corresponding ChromeDriver installed on your system.

## Features

- **Multi-Route and Multi-Date Scraping:** Scrape schedules across multiple routes and dates.
- **Threaded Execution:** Uses Python’s `ThreadPoolExecutor` for concurrent scraping.
- **Route Validation:** Checks whether a given route exists before scraping.
- **CSV Output:** Appends scraped data to a CSV file for further analysis.
- **Checkpointing:** (Optional) Resume scraping from the last saved checkpoint.

## Requirements

- **Python 3.7+**
- **Google Chrome**  
- **ChromeDriver**

## Installation

### 1. Clone the Repository

Clone this repository to your local machine:

```bash
git clone https://github.com/yourusername/your-repository.git
cd your-repository
```

### 2. Set Up a Virtual Environment

It’s recommended to use a virtual environment. For example, using `venv`:

On **macOS/Linux**:

```bash
python3 -m venv venv
source venv/bin/activate
```

On **Windows**:

```bash
python -m venv venv
venv\Scripts\activate
```

### 3. Install Python Dependencies

Install the required Python packages using `pip`:

```bash
pip install -r requirements.txt
```

### 4. Install ChromeDriver

The scraper requires ChromeDriver to control the Chrome browser. Ensure that the version of ChromeDriver matches your installed version of Google Chrome.

#### For Windows

1. Download ChromeDriver for Windows from the official site:  
   [ChromeDriver Downloads](https://chromedriver.chromium.org/downloads)
2. Extract the downloaded file.
3. Update the `CHROME_DRIVER_PATH` variable in the script (at the top of your Python file) with the full path to the `chromedriver.exe` file.

#### For macOS

1. Download ChromeDriver for macOS from the official site:  
   [ChromeDriver Downloads](https://chromedriver.chromium.org/downloads)
2. Extract the downloaded file.
3. You can either move the `chromedriver` binary to `/usr/local/bin` (or any folder in your `PATH`) **or** update the `CHROME_DRIVER_PATH` variable in the script with the full path to the binary.

#### For Linux

1. Download ChromeDriver for Linux from the official site:  
   [ChromeDriver Downloads](https://chromedriver.chromium.org/downloads)
2. Extract the downloaded file.
3. Move the `chromedriver` binary to a directory in your `PATH` (e.g., `/usr/local/bin`) **or** update the `CHROME_DRIVER_PATH` variable in the script accordingly.

### 5. Configure the Script

If needed, modify the configuration options in your Python script:

- **CSV_FILENAME**: The name of the CSV file where scraped schedules will be saved.
- **CHECKPOINT_FILE**: The JSON file used for checkpointing.
- **MAX_WORKERS**: Number of threads to use during scraping.
- **VALID_ROUTES_FILE**: The JSON file to store valid route mappings.
- **CHROME_DRIVER_PATH**: Set this to the full path of your ChromeDriver executable.

## Usage

To run the scraper, simply execute:

```bash
python your_script.py
```

The script will:

- Launch a headless Chrome browser.
- Discover valid routes based on the available locations.
- Scrape the schedules for each route over a specified date range.
- Save the results to the CSV file defined in `CSV_FILENAME`.

## Troubleshooting

- **ChromeDriver Errors:**  
  Ensure that your ChromeDriver version matches your installed version of Google Chrome. If you encounter connection or session errors, verify that the `CHROME_DRIVER_PATH` is set correctly.

- **Virtual Environment:**  
  Make sure you have activated your virtual environment before installing dependencies and running the script.

- **Dependencies:**  
  If you encounter module import errors, double-check that all dependencies are installed using the command:

  ```bash
  pip install -r requirements.txt
  ```

## Contributing

If you have suggestions for improvements or bug fixes, feel free to fork the repository and submit a pull request.

## License

This project is licensed under the [MIT License](LICENSE).

---

Happy scraping!

---

### How to Use These Files

1. **Clone and Set Up:**
   - Clone the repository.
   - Create and activate your virtual environment.
   - Install dependencies using `pip install -r requirements.txt`.

2. **Install ChromeDriver:**
   - Follow the instructions in the README to download and install the correct version of ChromeDriver for your operating system.
   - Update the `CHROME_DRIVER_PATH` variable in your script if necessary.

3. **Run the Script:**
   - Execute the Python script (e.g., `python your_script.py`) to start scraping ferry schedules.

This README should provide clear guidance to new users on setting up their environment, installing dependencies, and running the scraper. Feel free to customize it further to suit your project’s needs.
