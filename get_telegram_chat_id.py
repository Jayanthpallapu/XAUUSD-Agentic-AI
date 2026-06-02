import requests
import sys
import time
import os
import re

BOT_TOKEN = "8804445270:AAFCVyTZdWKdp2iMFPOWEkbBMMnXmG__a2o"
ENV_PATH = os.path.join(os.path.dirname(__file__), ".env")

def update_env_file(chat_id):
    if not os.path.exists(ENV_PATH):
        print(f"Error: .env file not found at {ENV_PATH}")
        return False
        
    with open(ENV_PATH, "r") as f:
        content = f.read()
        
    new_content = re.sub(
        r"TELEGRAM_CHAT_ID=.*",
        f"TELEGRAM_CHAT_ID={chat_id}",
        content
    )
    
    with open(ENV_PATH, "w") as f:
        f.write(new_content)
    return True

if __name__ == "__main__":
    print("--- Telegram Auto Chat ID Seeder ---")
    print("Checking for messages sent to your bot...")
    
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/getUpdates"
    
    found = False
    for attempt in range(5):
        try:
            res = requests.get(url, timeout=10)
            data = res.json()
            
            if not data.get("ok"):
                print(f"Telegram API Error: {data.get('description')}")
                break
                
            result = data.get("result", [])
            if result:
                latest = result[-1]
                message = latest.get("message") or latest.get("edited_message")
                if message:
                    chat = message.get("chat")
                    chat_id = chat.get("id")
                    username = chat.get("username", "N/A")
                    first_name = chat.get("first_name", "N/A")
                    
                    print(f"\n[SUCCESS] Successfully detected message from: {first_name} (@{username})")
                    print(f"Detected Chat ID: {chat_id}")
                    
                    print("Updating .env configuration file...")
                    if update_env_file(chat_id):
                        print("[v] .env successfully updated with your TELEGRAM_CHAT_ID!")
                    found = True
                    break
            else:
                print(f"Attempt {attempt+1}/5: No messages found yet. Please send a message to your bot on Telegram now...")
                time.sleep(3)
        except Exception as e:
            print(f"Error checking updates: {e}")
            break
            
    if not found:
        print("\n[x] Could not find any messages. Please make sure you search for your bot and click 'Start' or send it a text message first, then try again.")
        sys.exit(1)
