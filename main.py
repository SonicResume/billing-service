from fastapi import FastAPI, Request, HTTPException
import stripe
import os

app = FastAPI()

stripe.api_key = os.environ["STRIPE_SECRET_KEY"]
WEBHOOK_SECRET = os.environ["STRIPE_WEBHOOK_SECRET"]

PLAN_MAP = {
    "pro": 150,
    "business": 500,
    "premium": 999999,
}

@app.get("/")
def root():
    return {"status": "billing service running"}

@app.post("/stripe-webhook")
async def stripe_webhook(request: Request):

    payload = await request.body()
    sig = request.headers.get("stripe-signature")

    try:
        event = stripe.Webhook.construct_event(
            payload,
            sig,
            WEBHOOK_SECRET
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

    if event["type"] == "checkout.session.completed":
        session = event["data"]["object"]

        email = session.get("customer_details", {}).get("email")
        plan = session.get("metadata", {}).get("plan", "pro")

        credits = PLAN_MAP.get(plan, 0)

        print("🔥 PAYMENT SUCCESS")
        print("EMAIL:", email)
        print("PLAN:", plan)
        print("CREDITS:", credits)

    return {"ok": True}
