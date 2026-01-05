#!/usr/bin/env python3
# fetch_stream.py
# Bulk m3u8 extractor from FanCode highlights JSON
# Uses Selenium + CDP
# Output: m3u8.json

import os
import time
import json
import re
import requests
import shutil
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options

SOURCE_JSON = "https://raw.githubusercontent.com/cricstreamz745/Willow/refs/heads/main/output.json"
OUTPUT_FILE = "m3u8.json"

M3U8_RE = re.compile(r'https?://[^\'"\s>]+\.m3u8[^\'"\s>]*', re.I)

def extract_m3u8(text):
    return M3U8_RE.findall(text or "")

def make_driver():
    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.set_capability("goog:loggingPrefs", {"performance": "ALL"})
    return webdriver.Chrome(service=Service(shutil.which("chromedriver")), options=options)

def scrape_page(driver, url, timeout=20):
    found = set()
    driver.execute_cdp_cmd("Network.enable", {})
    driver.get(url)
    time.sleep(2)

    start = time.time()
    seen = set()

    while time.time() - start < timeout:
        for entry in driver.get_log("performance"):
            raw = entry.get("message")
            if not raw or raw in seen:
                continue
            seen.add(raw)

            try:
                msg = json.loads(raw)["message"]
            except:
                continue

            method = msg.get("method", "")
            params = msg.get("params", {})

            if method == "Network.requestWillBeSent":
                u = params.get("request", {}).get("url", "")
                if ".m3u8" in u:
                    found.add(u)

            if method == "Network.responseReceived":
                resp = params.get("response", {})
                u = resp.get("url", "")
                if ".m3u8" in u:
                    found.add(u)

        if found:
            break

        time.sleep(0.5)

    return sorted(found)

def main():
    print("▶ Fetching source JSON")
    data = requests.get(SOURCE_JSON, timeout=30).json()
    highlights = data.get("highlights", [])

    driver = make_driver()
    results = []
    total_links = 0

    try:
        for i, item in enumerate(highlights, 1):
            title = item.get("title")
            page_url = item.get("link")
            image = item.get("thumbnail")

            print(f"[{i}/{len(highlights)}] Scraping: {title}")
            m3u8 = scrape_page(driver, page_url)

            total_links += len(m3u8)

            results.append({
                "title": title,
                "target_url": page_url,
                "image": image,
                "m3u8": m3u8
            })

    finally:
        driver.quit()

    output = {
        "source": SOURCE_JSON,
        "total_pages": len(results),
        "total_m3u8": total_links,
        "results": results,
        "timestamp": int(time.time())
    }

    with open(OUTPUT_FILE, "w") as f:
        json.dump(output, f, indent=2)

    print(f"✅ Saved {total_links} m3u8 links → {OUTPUT_FILE}")

if __name__ == "__main__":
    main()
