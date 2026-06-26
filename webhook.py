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
        url = "https://reports.mylimobiz.com/SharedReport/CC395C73-8F55-4FCE-A397-BC2866AD0C55"
        headers = {"User-Agent": "Mozilla/5.0"}
        resp = requests.get(url, headers=headers, timeout=15)
        resp.raise_for_status()

        soup = BeautifulSoup(resp.text, 'html.parser')
        text = soup.get_text(separator="\n", strip=True)
        lines = [line.strip() for line in text.splitlines() if line.strip()]

        q = query.lower().strip()
        today_str = datetime.now().strftime("%m/%d/%Y")

        # Group raw layout into individual trip data blocks cleanly
        blocks = []
        current_block = []
        
        for line in lines:
            # When we hit a new date marker, save the old block and start fresh
            if re.match(r'^\d{2}/\d{2}/\d{4}$', line):
                if current_block:
                    blocks.append(current_block)
                current_block = [line]
            else:
                current_block.append(line)
        if current_block:
            blocks.append(current_block)

        # Filter blocks to only include today's current rides
        today_blocks = [b for b in blocks if b and b[0] == today_str]

        # 1. MANIFEST Command
        if q in ["manifest", "all", "list"]:
            entries = []
            for b in today_blocks:
                block_text = "\n".join(b)
                # Parse passenger (usually line index 3 or 4 after the date/conf/time keys)
                pax = b[3] if len(b) > 3 else "Unknown Pax"
                driver = "N/A"
                phone = ""
                for i, l in enumerate(b):
                    if re.search(r'\(\d{3}\)', l):
                        phone = l
                        driver = b[i-1] if i > 0 else "N/A"
                        break
                entries.append(f"Pax: {pax}\nDriver: {driver} {phone}\n")
            return "\n---\n".join(entries[:25]) if entries else "No manifest entries found today."

        # 2. SHUTTLE Command
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

        # 3. PAX NAME Command
        matches = []
        for b in today_blocks:
            block_text = "\n".join(b).lower()
            if q in block_text:
                driver = "N/A"
                phone = ""
                pax_name = b[3] if len(b) > 3 else "Passenger"
                for i, l in enumerate(b):
                    if re.search(r'\(\d{3}\)', l):
                        phone = l
                        driver = b[i-1] if i > 0 else "N/A"
                        break
                matches.append(f"Pax: {pax_name}\nDriver: {driver}\nPhone: {phone}")
        
        if matches:
            return "\n\n---\n\n".join(matches)
        else:
            return f"No driver or passenger found matching '{query}' for today."

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
