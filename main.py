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

    spreadsheet = client.open("DATA_BASE_REQUEST")

    vendors_sheet = spreadsheet.worksheet("vendors")
    projects_sheet = spreadsheet.worksheet("projects")
    payment_requests_sheet = spreadsheet.worksheet("payment_request")

    print("GOOGLE SHEETS CONNECTED")

except Exception as e:

    print("GOOGLE SHEETS ERROR:", str(e))

    vendors_sheet = None
    projects_sheet = None
    payment_requests_sheet = None

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

        # NORMALIZAR NUMERO
        from_number = from_number.replace("+", "")
        from_number = from_number.replace(" ", "")
        from_number = from_number.replace("-", "")

        # FIX ARGENTINA
        if from_number.startswith("549"):
            from_number = "54" + from_number[3:]

        text = message["text"]["body"].strip()

        print("FROM:", from_number)
        print("MESSAGE:", text)

        # -----------------------------
        # VALIDAR SHEETS
        # -----------------------------

        if vendors_sheet is None:

            send_whatsapp_message(
                from_number,
                "Google Sheets connection failed."
            )

            return {"status": "error"}

        # -----------------------------
        # GET VENDOR
        # -----------------------------

        vendors = vendors_sheet.get_all_records()

        vendor_found = None

        for vendor in vendors:

            phone = str(vendor["phone_number"])

            phone = phone.replace("+", "")
            phone = phone.replace(" ", "")
            phone = phone.replace("-", "")

            # FIX ARGENTINA
            if phone.startswith("549"):
                phone = "54" + phone[3:]

            if phone == from_number:

                vendor_found = vendor
                break

        if vendor_found is None:

            send_whatsapp_message(
                from_number,
                "❌ Your number is not registered."
            )

            return {"status": "error"}

        vendor_id = vendor_found["vendor_id"]
        vendor_name = vendor_found["vendor_name"]

        # -----------------------------
        # GET ACTIVE PROJECTS
        # -----------------------------

        projects = projects_sheet.get_all_records()

        active_projects = []

        for project in projects:

            if (
                project["vendor_id"] == vendor_id
                and str(project["active"]).upper() == "YES"
            ):

                active_projects.append(project)

        # -----------------------------
        # GET PENDING REQUESTS
        # -----------------------------

        payment_requests = payment_requests_sheet.get_all_records()

        blocked_project_ids = []

        for request_row in payment_requests:

            if (
                request_row["vendor_id"] == vendor_id
                and str(request_row["status"]).lower() == "pending"
            ):

                blocked_project_ids.append(
                    request_row["project_id"]
                )

        # -----------------------------
        # FILTER AVAILABLE PROJECTS
        # -----------------------------

        available_projects = []

        for project in active_projects:

            if project["project_id"] not in blocked_project_ids:

                available_projects.append(project)

        # -----------------------------
        # BUILD RESPONSE
        # -----------------------------

        if len(available_projects) == 0:

            response_message = (
                f"Hola {vendor_name} 👋\n\n"
                "No tienes proyectos disponibles para nuevos payment requests."
            )

        else:

            response_message = (
                f"Hola {vendor_name} 👋\n\n"
                "Estos son tus proyectos disponibles:\n\n"
            )

            for index, project in enumerate(available_projects, start=1):

                response_message += (
                    f"{index}. {project['project_name']}\n"
                    f"Balance: ${project['available_balance']}\n\n"
                )

            response_message += (
                "Responde con el número del proyecto."
            )

        send_whatsapp_message(
            from_number,
            response_message
        )

    except Exception as e:

        print("ERROR:", str(e))

    return {"status": "ok"}