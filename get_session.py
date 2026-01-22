from playwright.sync_api import sync_playwright
import json

STORAGE_FILE = 'session_storage.json'

def save_session():
    with sync_playwright() as p:
        # Use a temporary browser profile for login
        browser = p.chromium.launch(headless=False)
        context = browser.new_context()
        page = context.new_page()
        
        print("Navigating to Blackboard...")
        page.goto('https://learning.westminster.ac.uk/ultra/stream')
        
        print("Please log in manually via Microsoft SSO.")
        print("Once you are looking at your Activity Stream, press ENTER here.")
        
        input("\n>>> Press ENTER after you see your Activity Stream... ")
        
        # Save the session state (cookies + localStorage) to a portable JSON file
        storage = context.storage_state()
        with open(STORAGE_FILE, 'w') as f:
            json.dump(storage, f, indent=2)
        
        print(f"✅ Session saved to {STORAGE_FILE}")
        print("Now commit and push this file to GitHub!")
        
        context.close()
        browser.close()

if __name__ == "__main__":
    save_session()