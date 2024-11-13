import json
import requests
from bs4 import BeautifulSoup
from datetime import datetime
from urllib.parse import urlparse, parse_qs, urlunparse, urlencode

# WCA URLs
URL = "https://www.worldcubeassociation.org/competitions?region=Chile&search=&state=present&year=all+years&from_date=&to_date=&delegate=&display=list"
WCA_URL = "https://www.worldcubeassociation.org"


def fetch_tournaments(url: str, country: str) -> list:
    """
    Fetches tournaments from the WCA website based on the specified country.

    Parameters:
    url (str): Base WCA URL.
    country (str): Name or code of the country.

    Returns:
    list: List of dictionaries with tournament details.
    """
    try:
        country = format_country_for_url(country)
        url = url.replace("Chile", country)
        response = requests.get(url)
        response.raise_for_status()

        soup = BeautifulSoup(response.text, "html.parser")
        comp_elements = soup.find_all("span", class_="competition-info")
        date_elements = soup.find_all("span", class_="date")
        location_elements = soup.find_all("div", class_="location")

        if not comp_elements or not date_elements or not location_elements:
            print("No tournaments found.")
            return []

        tournaments = []
        for comp, date, location in zip(
            comp_elements, date_elements, location_elements
        ):
            link = comp.find("a")
            tournament_name = link.text.strip()
            tournament_url = WCA_URL + link["href"]

            date_str = date.get_text(strip=True).replace(",", "")
            month = date_str.split(" ")[0].strip()
            year = date_str.split(" ")[-1]

            if "-" in date_str:
                start_date_str = f"{month} {date_str.split(' ')[1]} {year}"
                end_date_str = f"{month} {date_str.split(' ')[3]} {year}"
                start_date = datetime.strptime(start_date_str, "%b %d %Y").date()
                end_date = datetime.strptime(end_date_str, "%b %d %Y").date()
            else:
                start_date = datetime.strptime(date_str, "%b %d %Y").date()
                end_date = start_date

            location_name = location.get_text(strip=True).replace(country + ", ", "")

            tournament = {
                "Name": tournament_name,
                "URL": tournament_url,
                "Start Date": start_date,
                "End Date": end_date,
                "Location": location_name,
                "Country": country,
            }
            tournaments.append(tournament)

        return tournaments

    except requests.RequestException as e:
        print(f"HTTP request error: {e}")
        return []


def format_country_for_url(country: str) -> str:
    """
    Formats the country name or code to be URL-compatible for the WCA API.

    Parameters:
    country (str): Country name or code.

    Returns:
    str: Country formatted for URL usage.
    """
    countries = fetch_country_data()
    country = country.lower()

    # Special case for United States
    usa_variants = ["united states", "us", "usa", "estados unidos"]
    if country in usa_variants:
        return "USA"

    # Check for full country name
    country_names = [c["name"].lower() for c in countries["items"]]
    country_codes = [c["iso2Code"].lower() for c in countries["items"]]

    if country in country_names:
        return country.replace(" ", "+")

    if country in country_codes:
        return country_names[country_codes.index(country)].replace(" ", "+")

    print("No matches found. Defaulting to Chile...")
    return "Chile"


def fetch_country_data() -> dict:
    """
    Fetches country data from the WCA API and returns it in JSON format.

    Returns:
    dict: JSON formatted list of countries.
    """
    api_url = "https://raw.githubusercontent.com/robiningelbrecht/wca-rest-api/master/api/countries.json"
    response = requests.get(api_url)
    response.raise_for_status()
    return response.json()


def format_country_display(country: str) -> str:
    """
    Returns the display format of a country name.

    Parameters:
    country (str): Country name or code.

    Returns:
    str: Country name formatted for display.
    """
    if format_country_for_url(country) == "USA":
        return "United States"
    return format_country_for_url(country).title().replace("+", " ")


def validate_country(country: str) -> bool:
    """
    Checks if the given country exists in the WCA API.

    Parameters:
    country (str): Country name or code.

    Returns:
    bool: True if the country is valid, False otherwise.
    """
    countries = fetch_country_data()
    country_names = [c["name"].lower() for c in countries["items"]]
    country_codes = [c["iso2Code"].lower() for c in countries["items"]]
    country = format_country_display(country).lower()
    return (
        country in country_names
        or country in country_codes
        or country in ["united states", "us", "usa", "estados unidos"]
    )


def load_translations() -> dict:
    """
    Loads translations from a JSON file.

    Returns:
    dict: JSON formatted translations.
    """
    try:
        with open("./json/messages.json", "r", encoding="utf-8") as file:
            return json.load(file)
    except FileNotFoundError:
        print("Translation file messages.json not found.")
        return {}


def translate(language: str, key: str) -> str:
    """
    Returns translated text based on a key and language.

    Parameters:
    language (str): Language code for translation.
    key (str): Translation key.

    Returns:
    str: Translated text.
    """
    translations = load_translations()
    return translations.get(key, {}).get(
        language, f"Translation for key '{key}' not found."
    )


def load_languages() -> dict:
    """
    Loads available languages from the translations JSON file.

    Returns:
    dict: JSON formatted list of available languages.
    """
    translations = load_translations()
    return translations.get("Languages", {})


def validate_language(language: str) -> bool:
    """
    Checks if the given language is available in the translations JSON.

    Parameters:
    language (str): Language code.

    Returns:
    bool: True if the language is available, False otherwise.
    """
    languages = load_languages()
    return language in languages


def clean_yt_link(link: str) -> str:
    """
    Cleans a YouTube link by removing unnecessary query parameters.

    Parameters:
    link (str): The original YouTube link.

    Returns:
    str: The cleaned YouTube link.
    """
    parsed_link = urlparse(link)
    query_params = {
        k: v
        for k, v in parse_qs(parsed_link.query).items()
        if k not in {"list", "start_radio", "index", "t"}
    }
    new_query = urlencode(query_params, doseq=True)
    new_link = urlunparse(parsed_link._replace(query=new_query))
    return new_link
