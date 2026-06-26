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
        # 🔗 UPDATED: Pointing directly to your active live report link
        url = "https://reports.mylimobiz.com/SharedReport/CC395C73-8F55-4FCE-A397-BC2866AD0C55"
        headers = {"User-Agent": "Mozilla/5.0"}
        resp = requests.get(url, headers=headers, timeout=15)
        resp.raise_for_status()

        soup = BeautifulSoup(resp.text, 'html.parser')
        text = soup.get_text(separator="\n", strip=True)
        lines = [line.strip() for line in text.splitlines() if line.strip()]

        q = query.lower().strip()
        
        # 📆 Auto-calculates today's date structure dynamically
        today_str = datetime.now().strftime("%m/%d/%Y")

        # 1. Full Manifest
        if q in ["manifest", "all", "list"]:
            entries = []
            i = 0
            while i < len(lines):
                if any(p in lines[i] for p in ["Balletto", "McWater", "Pagliarulo", "Clev"]):
                    pax = lines[i]
                    service = next((l for l in lines[i:i+30] if any(s in l for s in ["Shu"])), "N/A")
                    driver = "N/A"
                    phone = ""
                    for j in range(i, min(i+30, len(lines))):
                        if re.search(r'\(\d{3}\)', lines[j]):
                            phone = lines[j]
                            driver = lines[j-1] if j > 0 else "N/A"
                            break
                    entries.append(f"{pax}\n{service}\n{driver} {phone}\n")
                i += 1
            return "\n".join(entries[:25]) if entries else "No manifest entries found today."

        # 2. SHUTTLE command
        if "shuttle" in q:
            matches = []
            current = []
            for line in lines:
                current.append(line)
                if today_str in line or "Trip Total" in line:
                    block = "\n".join(current)
                    if any(s in block for s in ["Shuttle", "Standby", "Media", "PI", "DWC"]):
                        service = next((l for l in current if any(s in l for s in ["Shutt"])), "N/A")
                        driver = "N/A"
                        phone = ""
                        for l in current:
                            if re.search(r'\(\d{3}\)', l):
                                phone = l
                                driver = current[current.index(l)-1] if current.index(l) > 0 else "N/A"
                                break
                        matches.append(f"{service}\n{driver} {phone}")
                    current = []
            return "\n\n---\n\n".join(matches) if matches else f"No shuttles found listed for {today_str}."

        # 3. PAX NAME command (only driver info)
        matches = []
        current = []
        for line in lines:
            current.append(line)
            if today_str in line or "Trip Total" in line:
                block = "\n".join(current)
                if q in block.lower():
                    driver = "N/A"
                    phone = ""
                    for l in current:
                        if re.search(r'\(\d{3}\)', l):
                            phone = l
                            driver = current[current.index(l)-1] if current.index(l) > 0 else "N/A"
                            break
                    matches.append(f"Driver: {driver}\n{phone}")
                current = []
        if matches:
            return "\n\n".join(matches)
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
