from fastapi import FastAPI, Request
import requests
import os
import json
import gspread
from datetime import datetime

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
    conversation_sheet = spreadsheet.worksheet("conversation_state")

    print("GOOGLE SHEETS CONNECTED")

except Exception as e:

    print("GOOGLE SHEETS ERROR:", str(e))

    vendors_sheet = None

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
# GET CONVERSATION
# -----------------------------

def get_conversation(phone_number):

    conversations = conversation_sheet.get_all_records()

    for row in conversations:

        if str(row["phone_number"]) == str(phone_number):
            return row

    return None

# -----------------------------
# SAVE CONVERSATION
# -----------------------------

def save_conversation(
    phone_number,
    current_step,
    selected_project_id="",
    requested_amount="",
    available_projects=""
):

    conversations = conversation_sheet.get_all_records()

    row_number = None

    for index, row in enumerate(conversations, start=2):

        if str(row["phone_number"]) == str(phone_number):

            row_number = index
            break

    if row_number:

        conversation_sheet.update(
            f"A{row_number}:E{row_number}",
            [[
                phone_number,
                current_step,
                selected_project_id,
                requested_amount,
                available_projects
            ]]
        )

    else:

        conversation_sheet.append_row([
            phone_number,
            current_step,
            selected_project_id,
            requested_amount,
            available_projects
        ])

# -----------------------------
# DELETE CONVERSATION
# -----------------------------

def delete_conversation(phone_number):

    conversations = conversation_sheet.get_all_records()

    for index, row in enumerate(conversations, start=2):

        if str(row["phone_number"]) == str(phone_number):

            conversation_sheet.delete_rows(index)
            break

# -----------------------------
# RECEIVE MESSAGE
# -----------------------------

@app.post("/webhook")
async def receive_message(request: Request):

    body = await request.json()

    print(json.dumps(body, indent=2))

    try:

        if "messages" not in body["entry"][0]["changes"][0]["value"]:
            return {"status": "ok"}

        message = body["entry"][0]["changes"][0]["value"]["messages"][0]

        from_number = message["from"]

        from_number = from_number.replace("+", "")
        from_number = from_number.replace(" ", "")
        from_number = from_number.replace("-", "")

        if from_number.startswith("549"):
            from_number = "54" + from_number[3:]

        text = message["text"]["body"].strip()

        # RESET CONVERSATION
        if text.lower() in ["hola", "menu", "reset", "start"]:

            delete_conversation(from_number)

        print("FROM:", from_number)
        print("MESSAGE:", text)

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
        # GET CONVERSATION STATE
        # -----------------------------

        conversation = get_conversation(from_number)

        # ======================================================
        # STEP 1 - START FLOW
        # ======================================================

        if conversation is None:

            projects = projects_sheet.get_all_records()

            active_projects = []

            for project in projects:

                if (
                    project["vendor_id"] == vendor_id
                    and str(project["active"]).upper() == "YES"
                ):

                    active_projects.append(project)

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

            available_projects = []

            for project in active_projects:

                if project["project_id"] not in blocked_project_ids:

                    available_projects.append(project)

            if len(available_projects) == 0:

                response_message = (
                    f"Hola {vendor_name} 👋\n\n"
                    "No tienes proyectos disponibles."
                )

                send_whatsapp_message(
                    from_number,
                    response_message
                )

                return {"status": "ok"}

            response_message = (
                f"Hola {vendor_name} 👋\n\n"
                "Estos son tus proyectos disponibles:\n\n"
            )

            project_ids = []

            for index, project in enumerate(available_projects, start=1):

                response_message += (
                    f"{index}. {project['project_name']}\n"
                    f"Balance: ${project['available_balance']}\n\n"
                )

                project_ids.append(
                    str(project["project_id"])
                )

            response_message += (
                "Responde con el número del proyecto."
            )

            save_conversation(
                from_number,
                "waiting_project",
                "",
                "",
                ",".join(project_ids)
            )

            send_whatsapp_message(
                from_number,
                response_message
            )

            return {"status": "ok"}

        current_step = conversation["current_step"]

        # ======================================================
        # STEP 2 - WAITING PROJECT
        # ======================================================

        if current_step == "waiting_project":

            if not text.isdigit():

                send_whatsapp_message(
                    from_number,
                    "❌ Responde solo con el número del proyecto."
                )

                return {"status": "ok"}

            selected_index = int(text)

            available_project_ids = (
                conversation["available_projects"]
                .split(",")
            )

            projects = projects_sheet.get_all_records()

            filtered_projects = []

            for project in projects:

                if str(project["project_id"]) in available_project_ids:

                    filtered_projects.append(project)

            if selected_index < 1 or selected_index > len(filtered_projects):

                send_whatsapp_message(
                    from_number,
                    "❌ Proyecto inválido."
                )

                return {"status": "ok"}

            selected_project = filtered_projects[selected_index - 1]

            project_id = selected_project["project_id"]

            save_conversation(
                from_number,
                "waiting_amount",
                project_id,
                "",
                conversation["available_projects"]
            )

            send_whatsapp_message(
                from_number,
                (
                    f"Proyecto seleccionado:\n"
                    f"{selected_project['project_name']}\n\n"
                    f"Balance disponible: "
                    f"${selected_project['available_balance']}\n\n"
                    f"¿Cuánto deseas solicitar?"
                )
            )

            return {"status": "ok"}

        # ======================================================
        # STEP 3 - WAITING AMOUNT
        # ======================================================

        if current_step == "waiting_amount":

            try:

                requested_amount = float(text)

            except:

                send_whatsapp_message(
                    from_number,
                    "❌ Ingresa un monto válido."
                )

                return {"status": "ok"}

            # ---------------------------------
            # GET SELECTED PROJECT
            # ---------------------------------

            projects = projects_sheet.get_all_records()

            selected_project = None

            for project in projects:

                if (
                    str(project["project_id"])
                    == str(conversation["selected_project_id"])
                ):

                    selected_project = project
                    break

            if selected_project is None:

                send_whatsapp_message(
                    from_number,
                    "❌ Proyecto no encontrado."
                )

                delete_conversation(from_number)

                return {"status": "ok"}

            available_balance = float(
                selected_project["available_balance"]
            )

            # ---------------------------------
            # VALIDATE AMOUNT
            # ---------------------------------

            if requested_amount > available_balance:

                send_whatsapp_message(
                    from_number,
                    (
                        "❌ El monto excede el balance disponible.\n\n"
                        f"Balance disponible: ${available_balance}\n\n"
                        "Ingresa un monto válido."
                    )
                )

                return {"status": "ok"}

            # ---------------------------------
            # SAVE AMOUNT
            # ---------------------------------

            save_conversation(
                from_number,
                "waiting_description",
                conversation["selected_project_id"],
                requested_amount,
                conversation["available_projects"]
            )

            send_whatsapp_message(
                from_number,
                "Describe el trabajo realizado."
            )

            return {"status": "ok"}

        # ======================================================
        # STEP 4 - WAITING DESCRIPTION
        # ======================================================

        if current_step == "waiting_description":

            description = text

            request_id = f"PR-{datetime.now().strftime('%H%M%S')}"

            payment_requests_sheet.append_row([
                request_id,
                vendor_id,
                conversation["selected_project_id"],
                conversation["requested_amount"],
                "Pending",
                "Week 1",
                description,
                datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            ])

            projects = projects_sheet.get_all_records()

            payment_requests = payment_requests_sheet.get_all_records()

            remaining_projects = []

            for project in projects:

                if (
                    project["vendor_id"] == vendor_id
                    and str(project["active"]).upper() == "YES"
                ):

                    has_pending = False

                    for request_row in payment_requests:

                        if (
                            request_row["vendor_id"] == vendor_id
                            and request_row["project_id"] == project["project_id"]
                            and str(request_row["status"]).lower() == "pending"
                        ):

                            has_pending = True
                            break

                    if not has_pending:

                        remaining_projects.append(project)

            if len(remaining_projects) > 0:

                project_ids = []

                for project in remaining_projects:

                    project_ids.append(
                        str(project["project_id"])
                    )

                save_conversation(
                    from_number,
                    "ask_another_request",
                    "",
                    "",
                    ",".join(project_ids)
                )

                send_whatsapp_message(
                    from_number,
                    (
                        "✅ Payment Request creado\n\n"
                        f"Request ID: {request_id}\n"
                        f"Status: Pending\n\n"
                        "¿Deseas crear otro request?\n\n"
                        "1. Sí\n"
                        "2. No"
                    )
                )

            else:

                send_whatsapp_message(
                    from_number,
                    (
                        "✅ Payment Request creado\n\n"
                        f"Request ID: {request_id}\n"
                        f"Status: Pending\n\n"
                        "No tienes más proyectos disponibles."
                    )
                )

                delete_conversation(from_number)

            return {"status": "ok"}

        # ======================================================
        # STEP 5 - ASK ANOTHER REQUEST
        # ======================================================

        if current_step == "ask_another_request":

            if text == "1":

                projects = projects_sheet.get_all_records()

                available_project_ids = (
                    conversation["available_projects"]
                    .split(",")
                )

                response_message = (
                    f"Hola {vendor_name} 👋\n\n"
                    "Estos son tus proyectos disponibles:\n\n"
                )

                filtered_projects = []

                for project in projects:

                    if str(project["project_id"]) in available_project_ids:

                        filtered_projects.append(project)

                for index, project in enumerate(filtered_projects, start=1):

                    response_message += (
                        f"{index}. {project['project_name']}\n"
                        f"Balance: ${project['available_balance']}\n\n"
                    )

                response_message += (
                    "Responde con el número del proyecto."
                )

                save_conversation(
                    from_number,
                    "waiting_project",
                    "",
                    "",
                    conversation["available_projects"]
                )

                send_whatsapp_message(
                    from_number,
                    response_message
                )

                return {"status": "ok"}

            else:

                send_whatsapp_message(
                    from_number,
                    "Perfecto 👌\n\nTus requests fueron enviados correctamente."
                )

                delete_conversation(from_number)

                return {"status": "ok"}

    except Exception as e:

        print("ERROR:", str(e))

    return {"status": "ok"}