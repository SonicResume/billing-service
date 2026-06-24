from fastapi import APIRouter, Request, HTTPException
import stripe

from config import STRIPE_SECRET_KEY, STRIPE_WEBHOOK_SECRET
from firebase import db
from billing import apply_plan

router = APIRouter()

stripe.api_key = STRIPE_SECRET_KEY


@router.post("/stripe/webhook")
async def stripe_webhook(request: Request):

    payload = await request.body()
    sig = request.headers.get("stripe-signature")

    try:
        event = stripe.Webhook.construct_event(
            payload,
            sig,
            STRIPE_WEBHOOK_SECRET
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

    if event["type"] == "checkout.session.completed":
        session = event["data"]["object"]

        email = session.get("customer_details", {}).get("email")
        plan = session.get("metadata", {}).get("plan", "pro")

        if email:
            apply_plan(db, email, plan)

            print("💰 PAYMENT SUCCESS")
            print(email, plan)

    return {"ok": True}
