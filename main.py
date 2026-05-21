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

        print("FULL DATA:", data)

        message = data["entry"][0]["changes"][0]["value"]["messages"][0]

        sender = message["from"]

        # limpiar formato
        sender = sender.replace("+", "").replace(" ", "")

        # fix para numeros de argentina
        if sender.startswith("549"):
            sender = "54" + sender[3:]

        print("SENDER FINAL:", sender)

        message_text = message["text"]["body"]

        print("MESSAGE:", message_text)

        send_whatsapp_message(
            sender,
            f"Hola 👋 Recibí tu mensaje: {message_text}"
        )

    except Exception as e:
        print("ERROR:", e)

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

    response = requests.post(
        url,
        headers=headers,
        json=data
    )

    print("WHATSAPP RESPONSE:", response.text)