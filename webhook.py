from flask import Flask, request
from twilio.twiml.messaging_response import MessagingResponse
import requests
from bs4 import BeautifulSoup
import re
from datetime import datetime

app = Flask(__name__)

# This global URL stays active. If you ever need to change it, you can text "URL: https://..." to the bot.
CURRENT_MANIFEST_URL = "https://mylimobiz.com"

def get_latest_driver_manifest(query=""):
    global CURRENT_MANIFEST_URL
    try:
        headers = {"User-Agent": "Mozilla/5.0"}
        resp = requests.get(CURRENT_MANIFEST_URL, headers=headers, timeout=15)
        resp.raise_for_status()

        soup = BeautifulSoup(resp.text, 'html.parser')
        text = soup.get_text(separator="\n", strip=True)
        lines = [line.strip() for line in text.splitlines() if line.strip()]

        q = query.lower().strip()
        
        # Automatically matches the current daily date layout dynamically (e.g., 06/26/2026)
        today_str = datetime.now().strftime("%m/%d/%Y")

        # 1. MANIFEST command (Provides Passenger Name + Driver Name & Number only)
        if q in ["manifest", "all", "list"]:
            entries = []
            i = 0
            while i < len(lines):
                # Restored the exact keyword scanning loop from your initial script
                if any(p in lines[i] for p in ["Balletto", "McWater", "Pagliarulo", "Clev", "Kornilov", "Liam"]):
                    pax = lines[i]
                    driver = "N/A"
                    phone = ""
                    for j in range(i, min(i+30, len(lines))):
                        if re.search(r'\(\d{3}\)', lines[j]):
                            phone = lines[j]
                            driver = lines[j-1] if j > 0 else "N/A"
                            break
                    entries.append(f"Pax: {pax}\nDriver: {driver} {phone}")
                i += 1
            return "\n\n---\n\n".join(entries[:25]) if entries else "No manifest entries found today."

        # 2. SHUTTLE command (Left untouched)
        if "shuttle" in q:
            matches = []
            current = []
            for line in lines:
                current.append(line)
                if today_str in line or "Trip Total" in line:
                    block = "\n".join(current)
                    if any(s in block for s in ["Shuttle", "Standby", "Media", "PI", "DWC"]):
                        service = next((l for l in current if any(s in l for s in ["Shutt", "Standby", "Media"])), "Shuttle")
                        driver = "N/A"
                        phone = ""
                        for l in current:
                            if re.search(r'\(\d{3}\)', l):
                                phone = l
                                driver = current[current.index(l)-1] if current.index(l) > 0 else "N/A"
                                break
                        matches.append(f"{service}\nDriver: {driver} {phone}")
                    current = []
            return "\n\n---\n\n".join(matches) if matches else "No shuttles found."

        # 3. PAX NAME command (Provides Passenger Name + Departure Time + Driver Details only)
        matches = []
        current = []
        for line in lines:
            current.append(line)
            if today_str in line or "Trip Total" in line:
                block = "\n".join(current)
                if q in block.lower():
                    # Parse specific target rows out of the matched card block safely
                    driver = "N/A"
                    phone = ""
                    pax_name = "Passenger"
                    pu_time = "N/A"
                    
                    # Extract the time layout entry (e.g., "09:26 PM")
                    for l in current:
                        if re.search(r'\d{2}:\d{2}\s*(?:AM|PM)', l, re.IGNORECASE):
                            pu_time = l
                        if re.search(r'\(\d{3}\)', l):
                            phone = l
                            driver = current[current.index(l)-1] if current.index(l) > 0 else "N/A"
                    
                    # Match name references directly within line indexes 
                    for l in current:
                        if q in l.lower() and not re.search(r'\(\d{3}\)', l) and l != driver:
                            pax_name = l
                            break
                            
                    matches.append(f"Pax: {pax_name}\nTime: {pu_time}\nDriver: {driver} {phone}")
                current = []
        
        if matches:
            return "\n\n---\n\n".join(matches)
        else:
            return f"No driver or passenger found matching '{query}'."

    except Exception as e:
        return f"System Fetch Error: {str(e)[:60]}"

@app.route("/webhook", methods=['GET', 'POST'])
def webhook():
    global CURRENT_MANIFEST_URL
    incoming_body = request.values.get('Body', '').strip()
    
    # URL auto-update utility check
    if incoming_body.lower().startswith("url:"):
        new_url = incoming_body[4:].strip()
        if new_url.startswith("http"):
            CURRENT_MANIFEST_URL = new_url
            resp = MessagingResponse()
            resp.message("✅ Bot link updated successfully.")
            return str(resp)

    resp = MessagingResponse()
    info = get_latest_driver_manifest(incoming_body)
    resp.message(info)
    return str(resp)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)

