import os
import sys
import zipfile
import requests
import json
import hashlib
from playwright.sync_api import sync_playwright

# Config
DB_FILE = 'seen_posts.json'

def send_telegram(message):
    """Send a message to Telegram. Returns True if successful."""
    url = f"https://api.telegram.org/bot{os.getenv('TG_TOKEN')}/sendMessage"
    payload = {"chat_id": os.getenv('TG_CHAT_ID'), "text": message, "parse_mode": "Markdown"}
    response = requests.post(url, json=payload)
    return response.ok

def test_telegram():
    """Send a test message to verify Telegram bot is working."""
    print("Testing Telegram connection...")
    if send_telegram("✅ *BB Monitor Test*\nYour Telegram bot is working correctly!"):
        print("✅ Test message sent successfully! Check your Telegram.")
    else:
        print("❌ Failed to send test message. Check your TG_TOKEN and TG_CHAT_ID.")


def run():
    # 1. Load seen posts history FIRST (before anything can fail)
    if os.path.exists(DB_FILE):
        with open(DB_FILE, 'r') as f:
            seen_ids = json.load(f)
    else:
        seen_ids = []
    
    try:
        # 2. Unzip session
        if os.path.exists('user_data.zip'):
            with zipfile.ZipFile('user_data.zip', 'r') as zip_ref:
                zip_ref.extractall('user_data')

        with sync_playwright() as p:
            context = p.chromium.launch_persistent_context('user_data', headless=True)
            page = context.new_page()
            
            try:
                page.goto('https://learning.westminster.ac.uk/ultra/stream', timeout=60000)
                page.wait_for_selector('.activity-stream', timeout=30000)
                
                items = page.query_selector_all('.activity-item')
                new_seen_count = 0
                
                for item in items[:10]:  # Check top 10 recent items
                    content = item.inner_text()
                    # Create a unique hash for this post content
                    post_id = hashlib.md5(content.encode()).hexdigest()
                    
                    if post_id not in seen_ids:
                        title = content.splitlines()[0]
                        send_telegram(f"📢 *New UoW Post:*\n{title}")
                        seen_ids.append(post_id)
                        new_seen_count += 1
                
            except Exception as e:
                print(f"Browser error: {e}")
            finally:
                context.close()
                
    except Exception as e:
        print(f"Setup error: {e}")
    finally:
        # ALWAYS save the seen_ids, no matter what happens above
        # This ensures GitHub Actions has a file to upload
        with open(DB_FILE, 'w') as f:
            json.dump(seen_ids[-50:], f)
        
        print(f"Successfully updated {DB_FILE} with {len(seen_ids)} IDs.")

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--test":
        test_telegram()
    else:
        run()