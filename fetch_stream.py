#!/usr/bin/env python3
# fetch_stream.py
# Bulk m3u8 extractor from HitMaal JSON
# Uses Selenium + Chrome DevTools Protocol
# Output: m3u8.json

import time
import json
import re
import requests
import shutil
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options

SOURCE_JSON = "https://raw.githubusercontent.com/cricstreamz745/Hit-Maal/refs/heads/main/hitmall.json"
OUTPUT_FILE = "m3u8.json"

M3U8_RE = re.compile(r'https?://[^\'"\s>]+\.m3u8[^\'"\s>]*', re.I)

# -------------------------------------------------
def make_driver():
    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")

    # Enable performance logs (CDP)
    options.set_capability(
        "goog:loggingPrefs",
        {"performance": "ALL"}
    )

    return webdriver.Chrome(
        service=Service(shutil.which("chromedriver")),
        options=options
    )

# -------------------------------------------------
def scrape_page(driver, url, timeout=25):
    found = set()
    seen_logs = set()

    driver.execute_cdp_cmd("Network.enable", {})
    driver.get(url)

    # ⏳ let scripts & player load
    time.sleep(4)

    start = time.time()

    while time.time() - start < timeout:
        for entry in driver.get_log("performance"):
            raw = entry.get("message")
            if not raw or raw in seen_logs:
                continue
            seen_logs.add(raw)

            try:
                msg = json.loads(raw)["message"]
            except Exception:
                continue

            method = msg.get("method", "")
            params = msg.get("params", {})

            if method in ("Network.requestWillBeSent", "Network.responseReceived"):
                url_found = (
                    params.get("request", {}).get("url")
                    or params.get("response", {}).get("url")
                )

                if url_found and ".m3u8" in url_found:
                    found.add(url_found)

        if found:
            break

        time.sleep(0.5)

    return sorted(found)

# -------------------------------------------------
def main():
    print("▶ Fetching source JSON")
    data = requests.get(SOURCE_JSON, timeout=30).json()

    # ✅ CORRECT KEY
    episodes = data.get("episodes", [])
    print(f"📦 Total episodes found: {len(episodes)}")

    driver = make_driver()
    results = []
    total_links = 0

    try:
        for i, item in enumerate(episodes, 1):
            title = item.get("title")
            page_url = item.get("link")
            image = item.get("thumbnail")

            if not page_url:
                continue

            print(f"[{i}/{len(episodes)}] Scraping: {title}")

            m3u8_links = scrape_page(driver, page_url)

            total_links += len(m3u8_links)

            results.append({
                "title": title,
                "target_url": page_url,
                "image": image,
                "m3u8": m3u8_links
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

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2)

    print(f"✅ Saved {total_links} m3u8 links → {OUTPUT_FILE}")

# -------------------------------------------------
if __name__ == "__main__":
    main()
