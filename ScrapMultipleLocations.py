#!/usr/bin/env python
# -*- coding: utf-8 -*-

import requests
from lxml import html
import csv
import argparse
import time

timezone = "PST"

def get_last_page_number(url, headers):
    response = requests.get(url, verify=True, headers=headers)
    if response.status_code == 200:
        parser = html.fromstring(response.text)
        last_page_number_xpath = "//div[@class='pagination']//ul/li[last()-1]//text()"
        try:
            last_page_number = int(parser.xpath(last_page_number_xpath)[0])
            return last_page_number
        except IndexError:
            return 1
    return None

headers = {
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8',
    'Accept-Encoding': 'gzip, deflate, br',
    'Accept-Language': 'en-GB,en;q=0.9,en-US;q=0.8,ml;q=0.7',
    'Cache-Control': 'max-age=0',
    'Connection': 'keep-alive',
    'Host': 'www.yellowpages.com',
    'Upgrade-Insecure-Requests': '1',
    'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/64.0.3282.140 Safari/537.36'
}

def remove_commas(data):
    """Removes commas from all string values in a dictionary."""
    return {key: value.replace(',', '') if isinstance(value, str) else value for key, value in data.items()}


def parse_listing(original_keyword, place, page):
    url = f"https://www.yellowpages.com/search?search_terms={original_keyword}&geo_location_terms={place}&page={page}"

    print("Retrieving", url)

    for retry in range(10):
        try:
            response = requests.get(url, verify=True, headers=headers)
            if response.status_code == 200:
                parser = html.fromstring(response.text)
                parser.make_links_absolute("https://www.yellowpages.com")

                XPATH_LISTINGS = "//div[@class='search-results organic']//div[@class='v-card']"
                listings = parser.xpath(XPATH_LISTINGS)
                scraped_results = []

                for results in listings:
                    XPATH_BUSINESS_NAME = ".//a[@class='business-name']//text()"
                    XPATH_TELEPHONE = ".//div[@class='phones phone primary']//text()"
                    XPATH_STREET = ".//div[@class='street-address']//text()"
                    XPATH_LOCALITY = ".//div[@class='locality']//text()"

                    business_name = ''.join(results.xpath(XPATH_BUSINESS_NAME)).strip()
                    telephone = ''.join(results.xpath(XPATH_TELEPHONE)).strip()
                    street = ''.join(results.xpath(XPATH_STREET)).strip()
                    locality = ''.join(results.xpath(XPATH_LOCALITY)).strip()

                    # Add timezone and IdStatus
                    business_details = {
                        'BusinessName': business_name,
                        'Phone': telephone,
                        'Address': street,
                        'Location': locality,
                        'Industry': original_keyword,  # Use the original keyword
                        'TimeZone': timezone,  # Default value; update as needed
                        'IdStatus': 5  # Default value
                    }
                    business_details = remove_commas(business_details)
                    scraped_results.append(business_details)

                return scraped_results

            elif response.status_code == 404:
                print(f"No results found for {original_keyword} in {place}")
                break
            else:
                print("Failed to process the page.")
                return []

        except Exception as e:
            print(f"Error occurred: {e}")
            time.sleep(1)
    return []



if __name__ == "__main__":
    import urllib.parse  # Import for encoding spaces as '+'

    argparser = argparse.ArgumentParser()
    argparser.add_argument('keywords_csv_file', help='CSV file with keywords')
    argparser.add_argument('places_csv_file', help='CSV file with places')

    args = argparser.parse_args()

    # Read the list of keywords from the provided CSV file
    with open(args.keywords_csv_file, "r", encoding="utf-8") as f:
        reader = csv.reader(f)
        keywords = [(row[0], urllib.parse.quote_plus(row[0])) for row in reader]  # Store original and encoded keywords


    # Read the list of places from the provided CSV file
    with open(args.places_csv_file, "r", encoding="utf-8") as f:
        reader = csv.reader(f)
        places = [row[0] for row in reader]

    for place in places:
        all_scraped_data = []  # Collect all data for this place

        for original_keyword, encoded_keyword in keywords:
            url = f"https://www.yellowpages.com/search?search_terms={encoded_keyword}&geo_location_terms={place}"
            last_page_number = get_last_page_number(url, headers)

            if last_page_number is not None:
                for page in range(1, last_page_number + 1):
                    print(f"Scraping page {page} of {last_page_number} for {original_keyword} in {place}")
                    scraped_data = parse_listing(original_keyword, place, page)
                    all_scraped_data.extend(scraped_data)
                    time.sleep(1)

        # Write all data for the current place (state) into a single file
        if all_scraped_data:
            output_file = f"{place}-yellowpages-scraped-data.csv"
            print(f"Writing data for {place} to {output_file}")
            with open(output_file, 'w', encoding="utf-8", newline='') as csvfile:
                fieldnames = [
                    'BusinessName', 'Phone', 'Address', 'Location', 'Industry', 'TimeZone', 'IdStatus'
                ]
                writer = csv.DictWriter(csvfile, fieldnames=fieldnames, quoting=csv.QUOTE_ALL)
                writer.writeheader()
                for data in all_scraped_data:
                    writer.writerow(data)

