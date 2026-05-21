from fastapi import FastAPI, Request
import requests
import os

app = FastAPI()

VERIFY_TOKEN = os.getenv("VERIFY_TOKEN")
WHATSAPP_TOKEN = os.getenv("WHATSAPP_TOKEN")
PHONE_NUMBER_ID = os.getenv("PHONE_NUMBER_ID")


@app.get("/")
def home():
    return {"message": "Vendor Payment Bot Running"}


@app.get("/webhook")
async def verify_webhook(request: Request):

    mode = request.query_params.get("hub.mode")
    token = request.query_params.get("hub.verify_token")
    challenge = request.query_params.get("hub.challenge")

    if mode and token:

        if mode == "subscribe" and token == VERIFY_TOKEN:
            return int(challenge)

    return {"error": "Verification failed"}


@app.post("/webhook")
async def webhook(request: Request):

    data = await request.json()

    try:

        entry = data["entry"][0]
        changes = entry["changes"][0]
        value = changes["value"]

        messages = value.get("messages")

        if messages:

            phone_number = messages[0]["from"]
            message_text = messages[0]["text"]["body"]

            send_whatsapp_message(
                phone_number,
                f"Recibí tu mensaje: {message_text}"
            )

    except Exception as e:
        print(e)

    return {"status": "received"}


def send_whatsapp_message(to, message):

    url = f"https://graph.facebook.com/v20.0/{PHONE_NUMBER_ID}/messages"

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

    response = requests.post(url, headers=headers, json=data)

    print(response.text)