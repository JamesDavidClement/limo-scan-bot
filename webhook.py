from flask import Flask, request
from twilio.twiml.messaging_response import MessagingResponse
import requests
from bs4 import BeautifulSoup
import re
from datetime import datetime

app = Flask(__name__)

def log_incoming_activity(sender, message_body):
    try:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_entry = f"[{timestamp}] FROM: {sender} | TEXT: '{message_body}'\n"
        with open("sms_bot_activity.log", "a", encoding="utf-8") as f:
            f.write(log_entry)
    except Exception as e:
        print(f"❌ Logging error: {e}")

def get_latest_driver_manifest(query=""):
    try:
        url = "https://mylimobiz.com"
        headers = {"User-Agent": "Mozilla/5.0"}
        resp = requests.get(url, headers=headers, timeout=15)
        resp.raise_for_status()

        soup = BeautifulSoup(resp.text, 'html.parser')
        text = soup.get_text(separator="\n", strip=True)
        lines = [line.strip() for line in text.splitlines() if line.strip()]

        q = query.lower().strip()
        today_str = datetime.now().strftime("%m/%d/%Y")

        # 🧱 Parse raw lines into individual trip blocks cleanly
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

        # 📆 Filter for today's data blocks only
        today_blocks = [b for b in blocks if b and b[0] == today_str]

        # 1. MANIFEST COMMAND (Short & Simple: Pax/Shuttle Name + Driver Details)
        if q in ["manifest", "all", "list"]:
            entries = []
            for b in today_blocks:
                driver = "N/A"
                phone = ""
                pax_name = "Unknown Passenger"
                
                # Find driver phone index to lock coordinates
                for i, l in enumerate(b):
                    if re.search(r'\(\d{3}\)', l):
                        phone = l
                        driver = b[i-1] if i > 0 else "N/A"
                        
                        # Passenger name sits right above the "N/A" or Service block columns
                        if i >= 4:
                            pax_name = b[i-3]
                        break
                
                entries.append(f"Pax: {pax_name}\nDriver: {driver} {phone}")
            return "\n\n---\n\n".join(entries[:25]) if entries else "No manifest entries found today."

        # 2. SHUTTLE COMMAND (Left completely untouched)
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

        # 3. PAX NAME COMMAND (Pax Name + Pickup Time + Driver Details Only)
        matches = []
        for b in today_blocks:
            block_text = "\n".join(b).lower()
            if q in block_text:
                driver = "N/A"
                phone = ""
                pu_time = b[2] if len(b) > 2 else "N/A" # Extracts PU Time column value
                pax_name = "Unknown Passenger"
                
                for i, l in enumerate(b):
                    if re.search(r'\(\d{3}\)', l):
                        phone = l
                        driver = b[i-1] if i > 0 else "N/A"
                        if i >= 4:
                            pax_name = b[i-3]
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
    incoming_body = request.values.get('Body', '').strip()
    incoming_sender = request.values.get('From', 'UNKNOWN_NUMBER')
    
    log_incoming_activity(incoming_sender, incoming_body)
    print(f"Incoming SMS from {incoming_sender}: {incoming_body}")
    
    resp = MessagingResponse()
    info = get_latest_driver_manifest(incoming_body)
    resp.message(info)
    return str(resp)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)

