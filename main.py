from fastapi import FastAPI, Request

app = FastAPI()


@app.get("/")
def home():
    return {"message": "Vendor Payment Bot Running"}


@app.post("/webhook")
async def webhook(request: Request):

    data = await request.form()

    print(data)

    return {"status": "received"}