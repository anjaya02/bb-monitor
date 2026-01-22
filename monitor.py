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
                
                # Check if we landed on login page (session expired)
                current_url = page.url
                if 'login' in current_url.lower() or 'auth' in current_url.lower():
                    send_telegram("⚠️ *BB Monitor Alert*\n\n🔐 Your Blackboard session has *expired*!\n\nPlease refresh your session:\n1. Run `get_session.py` locally\n2. Push new `user_data.zip` to GitHub")
                    print("Session expired - login page detected")
                    raise Exception("Session expired - redirected to login page")
                
                page.wait_for_selector('.activity-stream', timeout=30000)
                
                items = page.query_selector_all('.stream-item')
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
                
                print(f"Checked {len(items)} items, found {new_seen_count} new posts.")
                
            except Exception as e:
                error_msg = str(e)
                print(f"Browser error: {error_msg}")
                
                # Send alert for timeout errors (likely session issue)
                if 'timeout' in error_msg.lower() or 'activity-stream' in error_msg.lower():
                    send_telegram("⚠️ *BB Monitor Alert*\n\n❌ Failed to load Activity Stream!\n\nThis usually means your session expired.\n\nPlease refresh your session:\n1. Run `get_session.py` locally\n2. Push new `user_data.zip` to GitHub")
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