from fastapi import FastAPI, Request
import requests
import os
import json
import gspread

from google.oauth2.service_account import Credentials

app = FastAPI()

VERIFY_TOKEN = os.getenv("VERIFY_TOKEN")
WHATSAPP_TOKEN = os.getenv("WHATSAPP_TOKEN")
PHONE_NUMBER_ID = os.getenv("PHONE_NUMBER_ID")
GOOGLE_CREDENTIALS = os.getenv("GOOGLE_CREDENTIALS")

# -----------------------------
# GOOGLE SHEETS
# -----------------------------

try:

    SCOPES = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive"
    ]

    creds_dict = json.loads(GOOGLE_CREDENTIALS)

    creds = Credentials.from_service_account_info(
        creds_dict,
        scopes=SCOPES
    )

    client = gspread.authorize(creds)

    sheet = client.open("DATA_BASE_REQUEST").worksheet("vendors")

    print("GOOGLE SHEETS CONNECTED")

except Exception as e:

    print("GOOGLE SHEETS ERROR:", str(e))

    sheet = None

# -----------------------------
# SEND WHATSAPP MESSAGE
# -----------------------------

def send_whatsapp_message(to, message):

    url = f"https://graph.facebook.com/v25.0/{PHONE_NUMBER_ID}/messages"

    headers = {
        "Authorization": f"Bearer {WHATSAPP_TOKEN}",
        "Content-Type": "application/json"
    }

    data = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "text",
        "text": {
            "body": message
        }
    }

    response = requests.post(
        url,
        headers=headers,
        json=data
    )

    print("WHATSAPP RESPONSE:", response.text)

# -----------------------------
# HOME
# -----------------------------

@app.get("/")
def home():
    return {"message": "Vendor Payment Bot Running"}

# -----------------------------
# WEBHOOK VERIFY
# -----------------------------

@app.get("/webhook")
async def verify_webhook(request: Request):

    params = request.query_params

    mode = params.get("hub.mode")
    token = params.get("hub.verify_token")
    challenge = params.get("hub.challenge")

    if mode == "subscribe" and token == VERIFY_TOKEN:
        return int(challenge)

    return {"error": "Verification failed"}

# -----------------------------
# RECEIVE MESSAGES
# -----------------------------

@app.post("/webhook")
async def receive_message(request: Request):

    body = await request.json()

    print(json.dumps(body, indent=2))

    try:

        message = body["entry"][0]["changes"][0]["value"]["messages"][0]

        from_number = message["from"]
        text = message["text"]["body"].strip()

        print("FROM:", from_number)
        print("MESSAGE:", text)

        if sheet is None:

            send_whatsapp_message(
                from_number,
                "Google Sheets connection failed."
            )

            return {"status": "error"}

        records = sheet.get_all_records()

        found = False

        for row in records:

            vendor = str(row["vendor_name"]).lower().strip()

            if vendor == text.lower():

                response_message = (
                    f"Vendor: {row['vendor_name']}\n"
                    f"Vendor ID: {row['vendor_id']}"
                )

                send_whatsapp_message(
                    from_number,
                    response_message
                )

                found = True
                break

        if not found:

            send_whatsapp_message(
                from_number,
                "Vendor not found."
            )

    except Exception as e:

        print("ERROR:", str(e))

    return {"status": "ok"}