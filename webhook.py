from flask import Flask, request
from twilio.twiml.messaging_response import MessagingResponse
import requests
from bs4 import BeautifulSoup
import re

app = Flask(__name__)

# Active, working manifest URL
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

        # 🧱 Group raw text rows into independent trip list blocks cleanly
        blocks = []
        current_block = []
        for line in lines:
            # Every trip block on Limo Anywhere starts with a date pattern (MM/DD/YYYY)
            if re.match(r'^\d{2}/\d{2}/\d{4}$', line):
                if current_block:
                    blocks.append(current_block)
                current_block = [line]
            else:
                current_block.append(line)
        if current_block:
            blocks.append(current_block)

        # 1. MANIFEST COMMAND (Returns every trip found on the page cleanly)
        if q in ["manifest", "all", "list"]:
            entries = []
            for b in blocks:
                driver = "N/A"
                phone = ""
                pax_name = "Unknown Passenger"
                
                for i, l in enumerate(b):
                    if re.search(r'\(\d{3}\)', l):
                        phone = l
                        driver = b[i-1] if i > 0 else "N/A"
                        # The passenger name usually occupies index position 4 in the block array layout
                        if len(b) > 4:
                            pax_name = b[4]
                        break
                entries.append(f"Pax: {pax_name}\nDriver: {driver} {phone}")
            return "\n\n---\n\n".join(entries[:25]) if entries else "The manifest link is currently completely empty."

        # 2. SHUTTLE COMMAND
        if "shuttle" in q:
            matches = []
            for b in blocks:
                block_text = "\n".join(b)
                if any(s in block_text for s in ["Shuttle", "Standby", "Media", "PI", "DWC"]):
                    service = next((l for l in b if any(s in l for s in ["Shuttle", "Standby", "Media"])), "Shuttle")
                    driver = "N/A"
                    phone = ""
                    for i, l in enumerate(b):
                        if re.search(r'\(\d{3}\)', l):
                            phone = l
                            driver = b[i-1] if i > 0 else "N/A"
                            break
                    matches.append(f"{service}\nDriver: {driver} {phone}")
            return "\n\n---\n\n".join(matches) if matches else "No shuttle rows found on this manifest page."

        # 3. PAX NAME COMMAND (Matches ANY passenger name typed dynamically)
        matches = []
        for b in blocks:
            block_text = "\n".join(b).lower()
            if q in block_text:
                driver = "N/A"
                phone = ""
                pu_time = "N/A"
                pax_name = "Unknown Passenger"
                
                # Extract pickup timestamp string safely
                for l in b:
                    if re.search(r'\d{2}:\d{2}\s*(?:AM|PM)', l, re.IGNORECASE):
                        pu_time = l
                        break
                
                for i, l in enumerate(b):
                    if re.search(r'\(\d{3}\)', l):
                        phone = l
                        driver = b[i-1] if i > 0 else "N/A"
                        break
                
                if len(b) > 4:
                    pax_name = b[4]
                    
                matches.append(f"Pax: {pax_name}\nTime: {pu_time}\nDriver: {driver} {phone}")
        
        if matches:
            return "\n\n---\n\n".join(matches)
        else:
            return f"Could not find any trips matching the name '{query}' on the active manifest."

    except Exception as e:
        return f"System Fetch Error: {str(e)[:60]}"

@app.route("/webhook", methods=['GET', 'POST'])
def webhook():
    global CURRENT_MANIFEST_URL
    incoming_body = request.values.get('Body', '').strip()
    
    # Text "URL: https://..." to rewrite the live link instantly
    if incoming_body.lower().startswith("url:"):
        new_url = incoming_body[4:].strip()
        if new_url.startswith("http"):
            CURRENT_MANIFEST_URL = new_url
            resp = MessagingResponse()
            resp.message("✅ Bot manifest link updated successfully.")
            return str(resp)

    resp = MessagingResponse()
    info = get_latest_driver_manifest(incoming_body)
    resp.message(info)
    return str(resp)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
