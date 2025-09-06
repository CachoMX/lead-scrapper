#!/usr/bin/env python
# -*- coding: utf-8 -*-

from playwright.async_api import async_playwright
import asyncio
import csv
import time
import random
import logging
import sys
import os
import json
from urllib.parse import urlencode
import requests
from datetime import datetime

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

class MultiSessionScraper:
    def __init__(self, timezone_file='pst.csv'):
        self.timezone_file = timezone_file
        self.timezone = self.get_timezone_from_file(timezone_file)
        self.proxies = self.load_proxy_list()
        self.all_results = []
    
    def get_timezone_from_file(self, filename):
        """Extract timezone from filename"""
        timezone_map = {
            'pst.csv': 'PST',
            'est.csv': 'EST', 
            'cst.csv': 'CST',
            'mst.csv': 'MST'
        }
        return timezone_map.get(filename, 'PST')
        
    def load_proxy_list(self):
        try:
            response = requests.get(
                'https://proxy.webshare.io/api/v2/proxy/list/download/qmdbkedkgvtgrenpwvkkqezvxftqmwtcgcpkcquu/-/any/sourceip/direct/-/?plan_id=10580741',
                timeout=30
            )
            proxies = []
            for line in response.text.split('\n'):
                if ':' in line.strip():
                    host, port = line.strip().split(':')
                    proxies.append({'server': f'http://{host}:{port}', 'id': f'{host}:{port}'})
            logging.info(f"Loaded {len(proxies)} proxies")
            return proxies
        except:
            return []
    
    async def scrape_single_page_new_session(self, keyword, place, page_num):
        """Scrape a single page using a completely new browser session"""
        playwright = None
        try:
            # Create fresh browser for each page
            playwright = await async_playwright().__aenter__()
            
            # Random proxy for this session
            proxy = random.choice(self.proxies) if self.proxies else None
            
            browser = await playwright.chromium.launch(
                headless=True,
                args=[
                    '--no-first-run',
                    '--disable-blink-features=AutomationControlled',
                    '--disable-web-security',
                    '--disable-dev-shm-usage',
                    '--no-sandbox'
                ],
                proxy=proxy
            )
            
            context = await browser.new_context(
                viewport={'width': 1920, 'height': 1080},
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
            )
            
            page = await context.new_page()
            
            # Stealth
            await page.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined});")
            
            # Build URL
            url = f"https://www.yellowpages.com/search?{urlencode({'search_terms': keyword, 'geo_location_terms': place, 'page': page_num})}"
            
            logging.info(f"NEW SESSION - Page {page_num}: {url} via {proxy['id'] if proxy else 'direct'}")
            
            # Navigate
            await page.goto(url, wait_until='domcontentloaded', timeout=60000)
            
            # Handle Cloudflare
            title = await page.title()
            if 'just a moment' in title.lower():
                logging.info(f"Page {page_num}: Cloudflare detected, waiting...")
                
                # Human simulation
                await page.mouse.move(random.randint(200, 600), random.randint(200, 400))
                await asyncio.sleep(random.uniform(2, 4))
                
                # Wait for completion
                try:
                    await page.wait_for_function(
                        "document.title !== 'Just a moment...'",
                        timeout=30000
                    )
                    logging.info(f"Page {page_num}: Cloudflare bypassed")
                except:
                    logging.error(f"Page {page_num}: Cloudflare timeout")
                    return []
            
            # Wait for content
            await asyncio.sleep(random.uniform(4, 7))
            
            # Extract listings
            listings = await page.evaluate(f"""
                () => {{
                    const selectors = ['.result', '[data-testid="organic-listing"]', '.search-results .result'];
                    let results = [];
                    
                    for (const selector of selectors) {{
                        results = document.querySelectorAll(selector);
                        if (results.length > 0) break;
                    }}
                    
                    if (results.length === 0) {{
                        // Check if page has business content
                        const bodyText = document.body.innerText.toLowerCase();
                        if (!bodyText.includes('business') && !bodyText.includes('phone')) {{
                            console.log('No business content found');
                        }}
                        return [];
                    }}
                    
                    const listings = [];
                    
                    for (let i = 0; i < results.length && i < 40; i++) {{
                        const result = results[i];
                        try {{
                            // Name
                            let name = '';
                            const nameSelectors = ['.business-name span', '.business-name', 'h3 a', 'h2 a'];
                            for (const sel of nameSelectors) {{
                                const elem = result.querySelector(sel);
                                if (elem && elem.textContent.trim()) {{
                                    name = elem.textContent.trim();
                                    break;
                                }}
                            }}
                            if (!name) continue;
                            
                            // Phone
                            let phone = '';
                            const phoneSelectors = ['.phone', '.phones', 'a[href*="tel:"]'];
                            for (const sel of phoneSelectors) {{
                                const elem = result.querySelector(sel);
                                if (elem) {{
                                    const phoneText = elem.textContent.replace(/\\D/g, '');
                                    if (phoneText.length >= 10) {{
                                        phone = phoneText;
                                        break;
                                    }}
                                }}
                            }}
                            
                            // Address
                            let address = '';
                            const addrElem = result.querySelector('.adr, .address');
                            if (addrElem) address = addrElem.textContent.trim();
                            
                            // Website
                            let website = '';
                            const webElem = result.querySelector('a[href*="http"]:not([href*="yellowpages.com"])');
                            if (webElem) website = webElem.href;
                            
                            // Categories
                            let categories = '';
                            const catElems = result.querySelectorAll('.categories a, .category');
                            if (catElems.length > 0) {{
                                categories = Array.from(catElems)
                                    .map(e => e.textContent.trim())
                                    .filter(c => c)
                                    .slice(0, 2)
                                    .join(', ');
                            }}
                            
                            listings.push({{
                                Name: name,
                                Phone: phone,
                                Address: address,
                                Website: website,
                                Category: categories,
                                Keyword: '{keyword}',
                                Location: '{place}',
                                TimeZone: '{self.timezone}',
                                IdStatus: 'Lead',
                            }});
                            
                        }} catch (error) {{
                            console.error('Extraction error:', error);
                        }}
                    }}
                    
                    return listings;
                }}
            """)
            
            if listings:
                logging.info(f"Page {page_num}: SUCCESS - {len(listings)} listings extracted")
            else:
                logging.warning(f"Page {page_num}: No listings found")
            
            return listings
            
        except Exception as e:
            logging.error(f"Page {page_num} error: {e}")
            return []
        finally:
            if playwright:
                try:
                    await browser.close()
                    await playwright.__aexit__(None, None, None)
                except:
                    pass
    
    async def scrape_multiple_pages_parallel(self, keyword, place, pages_to_scrape):
        """Scrape multiple pages in parallel using different browser sessions"""
        logging.info(f"Scraping {len(pages_to_scrape)} pages in parallel for '{keyword}' in {place}")
        
        # Limit concurrent sessions for low memory environments
        semaphore = asyncio.Semaphore(2)  # Reduced for Render's 512MB limit
        
        async def scrape_with_semaphore(page_num):
            async with semaphore:
                # Random delay to spread requests
                await asyncio.sleep(random.uniform(0, 5))
                return await self.scrape_single_page_new_session(keyword, place, page_num)
        
        # Create tasks for all pages
        tasks = [scrape_with_semaphore(page_num) for page_num in pages_to_scrape]
        
        # Execute all tasks
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Collect all listings
        all_listings = []
        successful_pages = 0
        
        for i, result in enumerate(results):
            page_num = pages_to_scrape[i]
            
            if isinstance(result, Exception):
                logging.error(f"Page {page_num} failed with exception: {result}")
            elif isinstance(result, list):
                all_listings.extend(result)
                if result:
                    successful_pages += 1
                    logging.info(f"Page {page_num}: Added {len(result)} listings")
        
        logging.info(f"PARALLEL SCRAPING COMPLETE: {len(all_listings)} total listings from {successful_pages} successful pages")
        return all_listings
    
    def save_results(self, results, filename):
        """Save results to CSV"""
        if not results:
            return
        
        fieldnames = ['Name', 'Phone', 'Address', 'Website', 'Category', 'Keyword', 'Location', 'TimeZone', 'IdStatus']
        
        with open(filename, 'w', encoding='utf-8', newline='') as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(results)
        
        logging.info(f"Saved {len(results)} results to {filename}")
    
    def send_to_webhook(self, results, filename):
        """Send results to N8N webhook"""
        webhook_url = "https://n8n.vixi.agency/webhook-test/188228af-16bd-43cc-905b-296fd36c4699"
        
        try:
            # Prepare data to send
            payload = {
                "filename": filename,
                "total_listings": len(results),
                "timezone": self.timezone,
                "timestamp": datetime.now().isoformat(),
                "data": results[:10]  # Send first 10 as preview
            }
            
            # Send as JSON
            response = requests.post(
                webhook_url,
                json=payload,
                headers={'Content-Type': 'application/json'},
                timeout=30
            )
            
            if response.status_code == 200:
                logging.info(f"Successfully sent {len(results)} results to N8N webhook")
            else:
                logging.error(f"Webhook failed with status {response.status_code}: {response.text}")
                
        except Exception as e:
            logging.error(f"Error sending to webhook: {e}")
    
    def send_csv_to_webhook(self, filename):
        """Send CSV file to N8N webhook"""
        webhook_url = "https://n8n.vixi.agency/webhook-test/188228af-16bd-43cc-905b-296fd36c4699"
        
        try:
            with open(filename, 'rb') as csv_file:
                files = {'file': (filename, csv_file, 'text/csv')}
                data = {
                    'timezone': self.timezone,
                    'timestamp': datetime.now().isoformat()
                }
                
                response = requests.post(
                    webhook_url,
                    files=files,
                    data=data,
                    timeout=60
                )
                
                if response.status_code == 200:
                    logging.info(f"Successfully sent CSV file {filename} to N8N webhook")
                else:
                    logging.error(f"CSV webhook failed with status {response.status_code}: {response.text}")
                    
        except Exception as e:
            logging.error(f"Error sending CSV to webhook: {e}")
    
    async def run_multi_session_scraper(self):
        """Run multi-session scraper"""
        if not self.proxies:
            logging.error("No proxies available")
            return
        
        # Load keywords and places
        keywords = []
        places = []
        
        try:
            with open('keywords.csv', 'r', encoding='utf-8') as f:
                keywords = [row[0].strip() for row in csv.reader(f) if row]
        except:
            keywords = ['Real Estate']
        
        try:
            with open(self.timezone_file, 'r', encoding='utf-8') as f:
                places = [row[0].strip() for row in csv.reader(f) if row]
        except:
            places = ['CA']
        
        logging.info(f"Starting multi-session scraper: {len(keywords)} keywords, {len(places)} places")
        
        for place in places:
            for keyword in keywords:
                start_time = time.time()
                
                print(f"\n{'='*70}")
                print(f"MULTI-SESSION SCRAPING: '{keyword}' in {place}")
                print(f"{'='*70}")
                
                # Define pages to scrape - reduced for memory limits
                pages_to_test = list(range(1, 21))  # Pages 1-20 (reduced for Render)
                
                # Scrape pages in parallel
                listings = await self.scrape_multiple_pages_parallel(keyword, place, pages_to_test)
                
                if listings:
                    self.all_results.extend(listings)
                    
                    # Save progress
                    timestamp = datetime.now().strftime("%H%M%S")
                    progress_file = f"multi_session_progress_{timestamp}.csv"
                    self.save_results(listings, progress_file)
                    
                    elapsed = time.time() - start_time
                    
                    print(f"\nRESULTS FOR '{keyword}' in {place}:")
                    print(f"Time taken: {elapsed:.1f} seconds")
                    print(f"Listings found: {len(listings)}")
                    print(f"Total pages scraped: {len(pages_to_test)}")
                    print(f"Saved to: {progress_file}")
                
                # Delay between keyword-place combinations
                delay = random.uniform(30, 60)
                print(f"Waiting {delay:.1f}s before next combination...")
                await asyncio.sleep(delay)
        
        # Final save and webhook
        if self.all_results:
            final_filename = f"multi_session_final_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
            self.save_results(self.all_results, final_filename)
            
            # Send to N8N webhook
            print("Sending results to N8N webhook...")
            self.send_to_webhook(self.all_results, final_filename)
            self.send_csv_to_webhook(final_filename)
            
            print(f"\n{'='*70}")
            print("MULTI-SESSION SCRAPING COMPLETED!")
            print(f"{'='*70}")
            print(f"Total listings collected: {len(self.all_results)}")
            print(f"Final results saved to: {final_filename}")
            print(f"Results sent to N8N webhook: {len(self.all_results)} listings")
            print(f"Average listings per page: {len(self.all_results)/100:.1f}")

def main():
    # Check command line arguments
    timezone_file = 'pst.csv'  # default
    
    if len(sys.argv) > 1:
        timezone_file = sys.argv[1]
        if not timezone_file.endswith('.csv'):
            timezone_file = f"{timezone_file}.csv"
    
    # Validate timezone file exists
    if not os.path.exists(timezone_file):
        print(f"Error: File '{timezone_file}' not found!")
        print("Available files: pst.csv, est.csv, cst.csv, mst.csv")
        print("Usage: python multi_session_scraper.py [pst|est|cst|mst]")
        return
    
    print(f"Starting scraper with timezone file: {timezone_file}")
    scraper = MultiSessionScraper(timezone_file)
    asyncio.run(scraper.run_multi_session_scraper())

if __name__ == '__main__':
    main()