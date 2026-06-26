from flask import Flask, request
from twilio.twiml.messaging_response import MessagingResponse
import requests
from bs4 import BeautifulSoup
from datetime import datetime
import os

app = Flask(__name__)

URL_FILE = "current_manifest_url.txt"
DEFAULT_URL = "https://reports.mylimobiz.com/SharedReport/CC395C73-8F55-4FCE-A397-BC2866AD0C55"

def get_current_url():
    if os.path.exists(URL_FILE):
        with open(URL_FILE, "r", encoding="utf-8") as f:
            url = f.read().strip()
            if url.startswith("http"):
                return url
    return DEFAULT_URL

def save_url(new_url):
    if new_url.startswith("http"):
        with open(URL_FILE, "w", encoding="utf-8") as f:
            f.write(new_url.strip())
        return True
    return False

def log_incoming_activity(sender, message_body):
    try:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_entry = f"[{timestamp}] FROM: {sender} | TEXT: '{message_body}'\n"
        with open("sms_bot_activity.log", "a", encoding="utf-8") as f:
            f.write(log_entry)
    except Exception as e:
        print(f"❌ Logging error: {e}")

def fetch_manifest(url):
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    resp = requests.get(url, headers=headers, timeout=15)
    resp.raise_for_status()
    return BeautifulSoup(resp.text, 'html.parser')

def parse_manifest_rows(soup):
    table = soup.find('table', id='AutoNumber2')
    if not table:
        return []
    rows = []
    data_rows = table.find_all('tr')[1:]
    for tr in data_rows:
        tds = tr.find_all('td')
        if len(tds) < 7:
            continue
        row = {
            'pu_date_conf': tds[0].get_text(strip=True).replace('\n', ' '),
            'pu_time_do': tds[1].get_text(strip=True).replace('\n', ' '),
            'routing': tds[2].get_text(strip=True),
            'passenger_trip': tds[3].get_text(strip=True).replace('\n', ' | '),
            'phone_service': tds[4].get_text(strip=True).replace('\n', ' | '),
            'vehicle': tds[5].get_text(strip=True),
            'driver': tds[6].get_text(strip=True).replace('\n', ' ')
        }
        rows.append(row)
    return rows

def get_shuttles(rows):
    shuttles = [row for row in rows if any(x in row['passenger_trip'].lower() for x in ['shuttle', 'standby', 'media', 'pi', 'dwc'])]
    if not shuttles:
        return "No shuttles found for today."
    response = [f"🚌 {row['passenger_trip']}\n⏰ {row['pu_time_do']}\n👤 {row['driver']}" for row in shuttles]
    return "\n\n---\n\n".join(response)

def get_manifest_summary(rows, limit=25):
    if not rows:
        return "No manifest entries found today."
    response = [f"📋 {row['passenger_trip']}\n⏰ {row['pu_time_do']}\n👤 {row['driver']}" for row in rows[:limit]]
    return "\n\n---\n\n".join(response)

def find_by_passenger(rows, query):
    q = query.lower().strip()
    matches = [row for row in rows if q in row['passenger_trip'].lower() or q in row['routing'].lower()]
    if not matches:
        return f"No records found for '{query}' today."
    response = [f"👤 {row['passenger_trip']}\n⏰ {row['pu_time_do']}\n👤 {row['driver']}" for row in matches]
    return "\n\n---\n\n".join(response)

@app.route("/webhook", methods=['GET', 'POST'])
def webhook():
    incoming_body = request.values.get('Body', '').strip()
    incoming_sender = request.values.get('From', 'UNKNOWN_NUMBER')
    log_incoming_activity(incoming_sender, incoming_body)
    
    resp = MessagingResponse()
    
    try:
        # Special command to update URL
        if incoming_body.lower().startswith("url:") or incoming_body.startswith("http"):
            new_url = incoming_body if incoming_body.startswith("http") else incoming_body[4:].strip()
            if save_url(new_url):
                resp.message(f"✅ Manifest URL updated successfully!\nNow using:\n{new_url}")
            else:
                resp.message("❌ Invalid URL format.")
            return str(resp)
        
        # Normal queries
        current_url = get_current_url()
        soup = fetch_manifest(current_url)
        rows = parse_manifest_rows(soup)
        
        body_lower = incoming_body.lower().strip()
        
        if body_lower in ["manifest", "all", "list", "full"]:
            info = get_manifest_summary(rows)
        elif "shuttle" in body_lower:
            info = get_shuttles(rows)
        else:
            info = find_by_passenger(rows, incoming_body)
            
    except Exception as e:
        info = f"System Fetch Error: {str(e)[:100]}"
    
    resp.message(info)
    return str(resp)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
