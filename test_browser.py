from playwright.sync_api import sync_playwright
import os

with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page()
    page.on("console", lambda msg: print(f"CONSOLE: {msg.text}"))
    page.on("pageerror", lambda err: print(f"PAGE ERROR: {err}"))
    page.goto("file://" + os.path.abspath("pipeline.html"))
    page.wait_for_timeout(2000)
    browser.close()
