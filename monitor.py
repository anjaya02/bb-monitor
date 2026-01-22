import os
import sys
import json
import hashlib
import requests
from datetime import datetime, timezone, timedelta
from playwright.sync_api import sync_playwright

# Config
DB_FILE = 'seen_posts.json'
HEALTH_CHECK_FILE = 'last_health_check.txt'
STORAGE_FILE = 'session_storage.json'
HEALTH_CHECK_INTERVAL_HOURS = 12  # Send health check every 12 hours (2/day)

# IST timezone (UTC+5:30)
IST = timezone(timedelta(hours=5, minutes=30))

def send_telegram(message):
    """Send a message to Telegram. Returns True if successful."""
    url = f"https://api.telegram.org/bot{os.getenv('TG_TOKEN')}/sendMessage"
    payload = {"chat_id": os.getenv('TG_CHAT_ID'), "text": message, "parse_mode": "Markdown"}
    response = requests.post(url, json=payload)
    return response.ok

def is_health_check_due():
    """Check if enough time has passed since last health check (12 hours)."""
    if not os.path.exists(HEALTH_CHECK_FILE):
        return True
    try:
        with open(HEALTH_CHECK_FILE, 'r') as f:
            last_check = datetime.fromisoformat(f.read().strip())
        hours_since = (datetime.now(timezone.utc) - last_check).total_seconds() / 3600
        return hours_since >= HEALTH_CHECK_INTERVAL_HOURS
    except:
        return True

def update_health_check_time():
    """Record the current time as the last health check."""
    with open(HEALTH_CHECK_FILE, 'w') as f:
        f.write(datetime.now(timezone.utc).isoformat())

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
        # Check for session storage file
        if not os.path.exists(STORAGE_FILE):
            send_telegram("⚠️ *BB Monitor Alert*\n\n❌ No session file found!\n\nPlease run `get_session.py` locally and push `session_storage.json` to GitHub.")
            print("No session_storage.json file found")
            return

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            
            # Load the portable session state
            with open(STORAGE_FILE, 'r') as f:
                storage_state = json.load(f)
            
            context = browser.new_context(storage_state=storage_state)
            page = context.new_page()
            
            try:
                print("Navigating to Blackboard...")
                page.goto('https://learning.westminster.ac.uk/ultra/stream', timeout=90000, wait_until='domcontentloaded')
                
                # Wait for initial page load
                page.wait_for_timeout(8000)
                current_url = page.url
                print(f"Initial URL: {current_url}")
                
                # Handle redirect state (page shows ?new_loc= but hasn't navigated yet)
                max_retries = 3
                for i in range(max_retries):
                    current_url = page.url
                    if 'new_loc=' in current_url:
                        print(f"Redirect state detected, waiting... (attempt {i+1}/{max_retries})")
                        page.wait_for_timeout(15000)  # Wait 15 seconds for redirect
                        
                        # Try to manually trigger the redirect
                        try:
                            # Extract the target URL from new_loc parameter
                            import urllib.parse
                            parsed = urllib.parse.urlparse(current_url)
                            params = urllib.parse.parse_qs(parsed.query)
                            if 'new_loc' in params:
                                target_path = params['new_loc'][0]
                                target_url = f"https://learning.westminster.ac.uk{target_path}"
                                print(f"Manually navigating to: {target_url}")
                                page.goto(target_url, timeout=30000, wait_until='domcontentloaded')
                                page.wait_for_timeout(5000)
                                break
                        except Exception as e:
                            print(f"Manual navigation failed: {e}")
                            # Try clicking the page body to trigger any pending navigation
                            try:
                                page.click('body', timeout=2000)
                            except:
                                pass
                    else:
                        break
                
                current_url = page.url
                print(f"Final URL: {current_url}")
                
                # Check if we landed on login page (session expired)
                if 'login' in current_url.lower() or 'auth' in current_url.lower() or 'microsoftonline' in current_url.lower():
                    send_telegram("⚠️ *BB Monitor Alert*\n\n🔐 Your Blackboard session has *expired*!\n\nPlease refresh your session:\n1. Run `get_session.py` locally\n2. Push new `session_storage.json` to GitHub")
                    print("Session expired - login page detected")
                    raise Exception("Session expired - redirected to login page")
                
                # Check if still stuck on redirect page - treat as session expiration
                if 'new_loc=' in current_url:
                    send_telegram("⚠️ *BB Monitor Alert*\n\n🔐 Session stuck on redirect page - likely *expired*!\n\nPlease refresh your session:\n1. Run `get_session.py` locally\n2. Push new `session_storage.json` to GitHub")
                    print("Still stuck on redirect page - session needs refresh")
                    raise Exception("Page stuck on redirect - session expired")
                
                # Try to find the activity stream with increased timeout
                print("Waiting for activity stream...")
                page.wait_for_selector('.activity-stream', timeout=60000)
                
                # Additional wait for stream items to load
                page.wait_for_timeout(3000)
                
                items = page.query_selector_all('.stream-item')
                print(f"Found {len(items)} stream items")
                new_seen_count = 0
                
                for item in items[:10]:  # Check top 10 recent items
                    content = item.inner_text()
                    # Create a unique hash for this post content
                    post_id = hashlib.md5(content.encode()).hexdigest()
                    
                    if post_id not in seen_ids:
                        title = content.splitlines()[0]
                        now_ist = datetime.now(IST)
                        send_telegram(f"📢 *New UoW Post*\n\n{title}\n\n🕐 {now_ist.strftime('%d %b %Y, %I:%M %p IST')}")
                        seen_ids.append(post_id)
                        new_seen_count += 1
                
                print(f"Checked {len(items)} items, found {new_seen_count} new posts.")
                
                # Health check - send only every 12 hours (2/day)
                if is_health_check_due():
                    now_ist = datetime.now(IST)
                    send_telegram(f"💚 *BB Monitor Health Check*\n\n✅ Bot is running normally\n📊 Tracking {len(seen_ids)} posts\n🕐 {now_ist.strftime('%d %b %Y, %I:%M %p IST')}")
                    update_health_check_time()
                    print("Sent health check (12-hour interval)")
                else:
                    print("Health check not due yet (sent within last 12 hours)")
                
            except Exception as e:
                error_msg = str(e)
                print(f"Browser error: {error_msg}")
                
                # Save screenshot for debugging
                try:
                    page.screenshot(path='error_screenshot.png')
                    print("Saved error screenshot to error_screenshot.png")
                except:
                    pass
                
                # Only send alert for genuine session/loading issues
                if 'timeout' in error_msg.lower() and 'activity-stream' in error_msg.lower():
                    send_telegram("⚠️ *BB Monitor Alert*\n\n❌ Failed to load Activity Stream (timeout).\n\nPossible causes:\n• Session expired\n• Blackboard is slow/down\n\nIf this persists, refresh your session.")
            finally:
                context.close()
                browser.close()
                
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