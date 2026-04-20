import asyncio
import uuid
from playwright.async_api import async_playwright

async def run():
    async with async_playwright() as p:
        browser = await p.webkit.launch(headless=True)
        context = await browser.new_context()
        page = await context.new_page()

        # Listen to all console logs
        page.on("console", lambda msg: print(f"CONSOLE: {msg.text}"))
        
        # Listen to all failed requests
        page.on("requestfailed", lambda request: print(f"REQ_FAILED: {request.url} - {request.failure}"))
        
        print("Navigating to login / register...")
        await page.goto("https://spitarmy.github.io/volume-tool-ryubee/login.html")
        await page.wait_for_load_state("networkidle")

        test_email = f"test_{uuid.uuid4().hex[:8]}@example.com"
        password = "password123"
        print(f"Creating new account: {test_email}")

        await page.evaluate("openRegister()")
        await page.fill("#reg-company", "Test Co")
        await page.fill("#reg-email", test_email)
        await page.fill("#reg-password", password)
        await page.fill("#reg-name", "Test User")
        await page.click("#register-btn")

        print("Waiting for navigation to home...")
        await page.wait_for_url("**/index.html", timeout=10000)

        print("Navigating to customers...")
        await page.goto("https://spitarmy.github.io/volume-tool-ryubee/customers.html")
        await page.wait_for_load_state("networkidle")
        await asyncio.sleep(3)
        
        print("Checking customerList content...")
        content = await page.inner_html("#customerList")
        if "Load failed" in content:
            print("FOUND LOAD FAILED IN HTML!")
        else:
            print("Did not find Load failed in HTML. Length of content:", len(content))
            
        await browser.close()

asyncio.run(run())
