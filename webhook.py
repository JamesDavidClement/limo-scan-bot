from flask import Flask, request
from twilio.twiml.messaging_response import MessagingResponse
import requests
from bs4 import BeautifulSoup
import re
import traceback

app = Flask(__name__)

CURRENT_MANIFEST_URL = "https://mylimobiz.com"

def get_latest_driver_manifest(query=""):
    global CURRENT_MANIFEST_URL
    
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    resp = requests.get(CURRENT_MANIFEST_URL, headers=headers, timeout=15)
    resp.raise_for_status()

    soup = BeautifulSoup(resp.text, 'html.parser')
    manifest_table = soup.find('table', {'id': 'AutoNumber2'})
    if not manifest_table:
        return "Error: Could not locate the manifest data table layout structure."

    rows = manifest_table.find_all('tr')
    trips = []

    for row in rows:
        cells = []
        for td in row.find_all('td'):
            cell_text = "\n".join([line.strip() for line in td.get_text(separator="\n").splitlines() if line.strip()])
            cells.append(cell_text)
        
        # Base table requirements: Must have 7 columns to be a valid data row
        if len(cells) != 7:
            continue
            
        # Clean header bypass check (Index 0 is the PU Date/Conf cell)
        if "pu date" in cells[0].lower():
            continue

        # Column 1 (Index 1): PU Time \n DO Time
        pu_time = cells[1].splitlines()[0] if cells[1].splitlines() else "N/A"

        # Column 3 (Index 3): Passenger(s) \n Trip Total
        pax_name = cells[3].splitlines()[0] if cells[3].splitlines() else "Blank"

        # Column 6 (Index 6): Driver Name \n Phone Number
        driver_lines = cells[6].splitlines()
        driver_name = "Unassigned"
        driver_phone = ""
        
        if driver_lines:
            driver_name = driver_lines[0]
            if len(driver_lines) > 1 and re.search(r'\(\d{3}\)', driver_lines[1]):
                driver_phone = driver_lines[1]
            elif re.search(r'\(\d{3}\)', driver_lines[0]):
                phone_match = re.search(r'\(\d{3}\)\s*\d{3}-\d{4}', driver_name)
                if phone_match:
                    driver_phone = phone_match.group(0)
                    driver_name = driver_name.replace(driver_phone, "").strip(" -,")

        trips.append({
            "time": pu_time,
            "pax": pax_name,
            "driver": driver_name,
            "phone": driver_phone
        })

    q = query.lower().strip()

    # 1. MANIFEST COMMAND
    if q in ["manifest", "all", "list"]:
        entries = []
        for t in trips:
            entries.append(f"Pax: {t['pax']}\nDriver: {t['driver']} {t['phone']}")
        return "\n\n---\n\n".join(entries[:25]) if entries else "The active manifest grid is empty."

    # 2. SHUTTLE COMMAND
    if "shuttle" in q:
        matches = []
        for t in trips:
            if any(s in t["pax"].lower() for s in ["shuttle", "standby", "media", "pi", "dwc"]):
                matches.append(f"{t['pax']}\nDriver: {t['driver']} {t['phone']}")
        return "\n\n---\n\n".join(matches) if matches else "No shuttle runs found on the current manifest."

    # 3. PAX NAME COMMAND
    matches = []
    for t in trips:
        if q in t["pax"].lower():
            matches.append(f"Pax: {t['pax']}\nTime: {t['time']}\nDriver: {t['driver']} {t['phone']}")
    
    if matches:
        return "\n\n---\n\n".join(matches)
    else:
        return f"No records matching '{query}' found on the current manifest."

@app.route("/webhook", methods=['GET', 'POST'])
def webhook():
    global CURRENT_MANIFEST_URL
    incoming_body = request.values.get('Body', '').strip()
    incoming_sender = request.values.get('From', 'UNKNOWN_NUMBER')
    
    print(f"Incoming SMS from {incoming_sender}: {incoming_body}")
    
    if incoming_body.lower().startswith("url:"):
        new_url = incoming_body[4:].strip()
        if new_url.startswith("http"):
            CURRENT_MANIFEST_URL = new_url
            resp = MessagingResponse()
            resp.message("✅ Bot link updated successfully.")
            return str(resp)

    resp = MessagingResponse()
    
    # 🛡️ Safety Net: If anything fails inside the parser, text back the exact error!
    try:
        info = get_latest_driver_manifest(incoming_body)
    except Exception as e:
        error_msg = f"Parser Error: {str(e)}"
        print(f"❌ Core Logic Error:\n{traceback.format_exc()}")
        info = error_msg
        
    resp.message(info)
    return str(resp)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
