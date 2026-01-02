#!/usr/bin/env python3
# fetch_stream_optimized.py
# Optimized Selenium + CDP .m3u8 capture
# Designed for GitHub Actions / CI
# Outputs m3u8.json

import os
import sys
import time
import json
import re
import shutil
import subprocess
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options

try:
    from webdriver_manager.chrome import ChromeDriverManager
    HAS_WDM = True
except Exception:
    HAS_WDM = False

DEFAULT_URL = "https://news.abplive.com/live-tv"
OUTPUT_FILE = "m3u8.json"

M3U8_RE = re.compile(
    r'https?://[^\'"\s>]+\.m3u8[^\'"\s>]*',
    flags=re.IGNORECASE
)

def now():
    return time.strftime("%H:%M:%S")

def extract_m3u8(text):
    if not text:
        return []
    return M3U8_RE.findall(text)

def find_chromedriver():
    env_path = os.getenv("CHROMEDRIVER_PATH")
    if env_path and shutil.which(env_path):
        return env_path

    path = shutil.which("chromedriver")
    if path:
        return path

    if HAS_WDM:
        try:
            return ChromeDriverManager(cache_valid_range=365).install()
        except Exception:
            pass

    return None

def make_driver(chromedriver_path):
    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--disable-extensions")
    options.add_argument("--disable-background-networking")
    options.add_argument("--disable-features=VizDisplayCompositor")
    options.add_experimental_option(
        "excludeSwitches", ["enable-automation"]
    )
    options.add_experimental_option("useAutomationExtension", False)

    options.set_capability(
        "goog:loggingPrefs", {"performance": "ALL"}
    )

    service = Service(chromedriver_path) if chromedriver_path else Service()
    driver = webdriver.Chrome(service=service, options=options)
    driver.set_page_load_timeout(
        int(os.getenv("STARTUP_TIMEOUT", "30"))
    )
    return driver

def main():
    target_url = (
        os.getenv("TARGET_URL")
        or (sys.argv[1] if len(sys.argv) > 1 else DEFAULT_URL)
    )

    MAX_WAIT = float(os.getenv("MAX_WAIT_SECONDS", "15"))
    POLL_INTERVAL = float(os.getenv("POLL_INTERVAL", "0.6"))

    print(f"{now()} ▶ Target URL: {target_url}")

    chromedriver = find_chromedriver()
    print(f"{now()} ▶ Chromedriver: {chromedriver}")

    driver = None
    found = set()

    try:
        driver = make_driver(chromedriver)

        try:
            driver.execute_cdp_cmd("Network.enable", {})
        except Exception:
            pass

        driver.get(target_url)
        time.sleep(1)

        start = time.time()
        processed = set()

        while time.time() - start < MAX_WAIT:
            try:
                logs = driver.get_log("performance")
            except Exception:
                logs = []

            for entry in logs:
                raw = entry.get("message")
                if not raw or raw in processed:
                    continue
                processed.add(raw)

                try:
                    msg = json.loads(raw)["message"]
                except Exception:
                    continue

                method = msg.get("method", "")
                params = msg.get("params", {})

                if method == "Network.requestWillBeSent":
                    url = params.get("request", {}).get("url", "")
                    if ".m3u8" in url.lower():
                        found.add(url)

                elif method == "Network.responseReceived":
                    resp = params.get("response", {})
                    url = resp.get("url", "")
                    mime = (resp.get("mimeType") or "").lower()

                    if ".m3u8" in url.lower():
                        found.add(url)

                    if any(x in mime for x in ["json", "javascript", "text", "html"]):
                        request_id = params.get("requestId")
                        if request_id:
                            try:
                                body = driver.execute_cdp_cmd(
                                    "Network.getResponseBody",
                                    {"requestId": request_id}
                                ).get("body", "")
                                for m in extract_m3u8(body):
                                    found.add(m)
                            except Exception:
                                pass

            if found:
                break

            time.sleep(POLL_INTERVAL)

    finally:
        if driver:
            driver.quit()

    output = {
        "target_url": target_url,
        "timestamp": int(time.time()),
        "count": len(found),
        "m3u8": sorted(found)
    }

    with open(OUTPUT_FILE, "w") as f:
        json.dump(output, f, indent=2)

    print(f"{now()} ✅ Saved {len(found)} links to {OUTPUT_FILE}")

    sys.exit(0 if found else 2)

if __name__ == "__main__":
    main()
