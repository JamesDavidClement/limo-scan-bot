from flask import Flask, request
from twilio.twiml.messaging_response import MessagingResponse
import requests
from bs4 import BeautifulSoup
import re

app = Flask(__name__)

# Primary active shared manifest URL link
CURRENT_MANIFEST_URL = "https://mylimobiz.com"

def get_latest_driver_manifest(query=""):
    global CURRENT_MANIFEST_URL
    try:
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
        resp = requests.get(CURRENT_MANIFEST_URL, headers=headers, timeout=15)
        resp.raise_for_status()

        soup = BeautifulSoup(resp.text, 'html.parser')
        
        # 🎯 Target the exact spreadsheet table ID from the page source
        manifest_table = soup.find('table', {'id': 'AutoNumber2'})
        if not manifest_table:
            return "Error: Could not locate the manifest data table layout."

        rows = manifest_table.find_all('tr')
        trips = []

        for row in rows:
            # Gather text from each cell row, preserving line breaks for easy parsing
            cells = []
            for td in row.find_all('td'):
                # Extract clean lines out of cell data blocks
                cell_text = "\n".join([line.strip() for line in td.get_text(separator="\n").splitlines() if line.strip()])
                cells.append(cell_text)
            
            # Skip empty lines, headers, or corrupted rows (Valid data rows have exactly 7 columns)
            if len(cells) != 7 or "pu date" in cells[0].lower():
                continue

            # Column 1 (Index 1) contains "PU Time \n DO Time". Isolate the first line for PU Time.
            time_lines = cells[1].splitlines()
            pu_time = time_lines[0] if time_lines else "N/A"

            # Column 3 (Index 3) contains "Passenger(s) \n Trip Total". Isolate the first line for the Pax/Shuttle label.
            pax_lines = cells[3].splitlines()
            pax_name = pax_lines[0] if pax_lines else "Blank"

            # Column 6 (Index 6) contains "Driver Name \n Phone Number". Separate them clearly.
            driver_lines = cells[6].splitlines()
            driver_name = "Unassigned"
            driver_phone = ""
            
            if driver_lines:
                driver_name = driver_lines[0]
                # Look for a phone number on the secondary line if available
                if len(driver_lines) > 1 and re.search(r'\(\d{3}\)', driver_lines[1]):
                    driver_phone = driver_lines[1]
                elif re.search(r'\(\d{3}\)', driver_lines[0]):
                    # If it's single line but has a phone number
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

        # 1. MANIFEST COMMAND (Short list of Pax Name + Driver Name & Number only)
        if q in ["manifest", "all", "list"]:
            entries = []
            for t in trips:
                entries.append(f"Pax: {t['pax']}\nDriver: {t['driver']} {t['phone']}")
            return "\n\n---\n\n".join(entries[:25]) if entries else "The active manifest grid is empty."

        # 2. SHUTTLE COMMAND (Extracts rows containing shuttle identifiers)
        if "shuttle" in q:
            matches = []
            for t in trips:
                if any(s in t["pax"].lower() for s in ["shuttle", "standby", "media", "pi", "dwc"]):
                    matches.append(f"{t['pax']}\nDriver: {t['driver']} {t['phone']}")
            return "\n\n---\n\n".join(matches) if matches else "No shuttle runs found on the current manifest."

        # 3. PAX NAME COMMAND (Extracts Pax Name + Departure Time + Driver Details only)
        matches = []
        for t in trips:
            if q in t["pax"].lower():
                matches.append(f"Pax: {t['pax']}\nTime: {t['time']}\nDriver: {t['driver']} {t['phone']}")
        
        if matches:
            return "\n\n---\n\n".join(matches)
        else:
            return f"No records matching '{query}' found on the current manifest."

    except Exception as e:
        return f"Grid Fetch Error: {str(e)[:60]}"

@app.route("/webhook", methods=['GET', 'POST'])
def webhook():
    global CURRENT_MANIFEST_URL
    incoming_body = request.values.get('Body', '').strip()
    
    # Text "URL: https://..." to update links dynamically over text
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
