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
        raise HTTPException(
            status_code=400,
            detail=f"Webhook verification failed: {str(e)}"
        )


    if event["type"] == "checkout.session.completed":

        session = event["data"]["object"]

        email = (
            session.get("customer_details", {}).get("email")
            or session.get("customer_email")
        )

        metadata = session.get("metadata", {})

        plan = metadata.get("plan")
        app_name = metadata.get("app", "noah-language")


        if not email:
            print("❌ No customer email found")
            return {"ok": True}


        if not plan:
            print("❌ Missing plan metadata")
            return {"ok": True}


        success = apply_plan(
            db,
            email,
            plan
        )


        if success:
            print("💰 PAYMENT SUCCESS")
            print("APP:", app_name)
            print("EMAIL:", email)
            print("PLAN:", plan)

        else:
            print("⚠️ Payment received but user not found")


    return {
        "ok": True
    }
