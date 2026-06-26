from flask import Flask, request
from twilio.twiml.messaging_response import MessagingResponse
import requests
from bs4 import BeautifulSoup
import re
from datetime import datetime

app = Flask(__name__)

# 🌐 Global variable fallback link cache
CURRENT_MANIFEST_URL = "https://mylimobiz.com"

def log_incoming_activity(sender, message_body):
    try:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_entry = f"[{timestamp}] FROM: {sender} | TEXT: '{message_body}'\n"
        with open("sms_bot_activity.log", "a", encoding="utf-8") as f:
            f.write(log_entry)
    except Exception as e:
        print(f"❌ Logging error: {e}")

def get_latest_driver_manifest(query=""):
    global CURRENT_MANIFEST_URL
    try:
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
        resp = requests.get(CURRENT_MANIFEST_URL, headers=headers, timeout=15)
        resp.raise_for_status()

        soup = BeautifulSoup(resp.text, 'html.parser')
        text = soup.get_text(separator="\n", strip=True)
        lines = [line.strip() for line in text.splitlines() if line.strip()]

        q = query.lower().strip()
        today_str = datetime.now().strftime("%m/%d/%Y")

        # Slice layout array into structured distinct trip records
        blocks = []
        current_block = []
        for line in lines:
            if re.match(r'^\d{2}/\d{2}/\d{4}$', line):
                if current_block:
                    blocks.append(current_block)
                current_block = [line]
            else:
                current_block.append(line)
        if current_block:
            blocks.append(current_block)

        # ✅ FIXED: Now checks index 0 (the date string inside the block) instead of checking the array list object
        today_blocks = [b for b in blocks if b and b[0] == today_str]

        # 1. MANIFEST COMMAND (Passenger Name + Driver Name & Number Only)
        if q in ["manifest", "all", "list"]:
            entries = []
            for b in today_blocks:
                driver = "N/A"
                phone = ""
                pax_name = "Unknown Passenger"
                
                for i, l in enumerate(b):
                    if re.search(r'\(\d{3}\)', l):
                        phone = l
                        driver = b[i-1] if i > 0 else "N/A"
                        break
                
                if len(b) > 4:
                    pax_name = b[4] # Safely pulls the Passenger/Trip text row coordinate
                
                entries.append(f"Pax: {pax_name}\nDriver: {driver} {phone}")
            return "\n\n---\n\n".join(entries[:25]) if entries else f"No manifest records available for {today_str}."

        # 2. SHUTTLE COMMAND (Untouched)
        if "shuttle" in q:
            matches = []
            for b in today_blocks:
                block_text = "\n".join(b)
                if any(s in block_text for s in ["Shuttle", "Standby", "Media", "PI", "DWC"]):
                    service = next((l for l in b if any(s in l for s in ["Shuttle", "Standby", "Media", "PI", "DWC"])), "Charter")
                    driver = "N/A"
                    phone = ""
                    for i, l in enumerate(b):
                        if re.search(r'\(\d{3}\)', l):
                            phone = l
                            driver = b[i-1] if i > 0 else "N/A"
                            break
                    matches.append(f"{service}\nDriver: {driver} {phone}")
            return "\n\n---\n\n".join(matches) if matches else f"No shuttles found listed for {today_str}."

        # 3. PAX NAME COMMAND (Passenger Name + Departure Time + Driver Details Only)
        matches = []
        for b in today_blocks:
            block_text = "\n".join(b).lower()
            if q in block_text:
                driver = "N/A"
                phone = ""
                pu_time = b[2] if len(b) > 2 else "N/A"  # Slices pickup time column string cleanly
                pax_name = b[4] if len(b) > 4 else "Unknown Passenger"
                
                for i, l in enumerate(b):
                    if re.search(r'\(\d{3}\)', l):
                        phone = l
                        driver = b[i-1] if i > 0 else "N/A"
                        break
                
                matches.append(f"Pax: {pax_name}\nTime: {pu_time}\nDriver: {driver} {phone}")
        
        if matches:
            return "\n\n---\n\n".join(matches)
        else:
            return f"No records matching '{query}' found for today."

    except Exception as e:
        return f"System Fetch Error: {str(e)[:60]}"

@app.route("/webhook", methods=['GET', 'POST'])
def webhook():
    global CURRENT_MANIFEST_URL
    incoming_body = request.values.get('Body', '').strip()
    incoming_sender = request.values.get('From', 'UNKNOWN_NUMBER')
    
    log_incoming_activity(incoming_sender, incoming_body)
    print(f"Incoming SMS from {incoming_sender}: {incoming_body}")
    
    # 🔄 AUTOMATION TOOL: Overwrite the active web URL remotely via a simple text message
    if incoming_body.lower().startswith("url:"):
        new_url = incoming_body[4:].strip()
        if new_url.startswith("http"):
            CURRENT_MANIFEST_URL = new_url
            resp = MessagingResponse()
            resp.message(f"✅ Bot target manifest URL successfully updated to: {CURRENT_MANIFEST_URL}")
            return str(resp)

    resp = MessagingResponse()
    info = get_latest_driver_manifest(incoming_body)
    resp.message(info)
    return str(resp)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
