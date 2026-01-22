from playwright.sync_api import sync_playwright

def save_session():
    with sync_playwright() as p:
        # This creates a folder named 'user_data' to store your session
        context = p.chromium.launch_persistent_context('user_data', headless=False)
        page = context.new_page()
        
        print("Navigating to Blackboard...")
        page.goto('https://learning.westminster.ac.uk/ultra/stream')
        
        print("Please log in manually via Microsoft SSO.")
        print("Once you are looking at your Activity Stream, close the browser window.")
        
        # This keeps the script running until you close the browser
        page.wait_for_timeout(300000) # 5-minute limit for you to log in
        context.close()

if __name__ == "__main__":
    save_session()