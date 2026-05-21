from fastapi import FastAPI, Request

app = FastAPI()

VERIFY_TOKEN = "vendor_secret_123"


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

    print(data)

    return {"status": "received"}