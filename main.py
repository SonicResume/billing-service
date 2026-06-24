from fastapi import FastAPI, Request, HTTPException
import stripe
import os
import json
import firebase_admin
from dotenv import load_dotenv
from firebase_admin import credentials, firestore

# -----------------------------
# INIT
# -----------------------------
load_dotenv()

app = FastAPI()

stripe.api_key = os.getenv("STRIPE_SECRET_KEY")
WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET")

# -----------------------------
# FIREBASE INIT (PRODUCTION SAFE)
# -----------------------------
firebase_json_str = os.getenv("FIREBASE_KEY")

if not firebase_json_str:
    raise Exception("FIREBASE_KEY env variable missing")

firebase_json = json.loads(firebase_json_str)

cred = credentials.Certificate(firebase_json)

if not firebase_admin._apps:
    firebase_admin.initialize_app(cred)

db = firestore.client()

# -----------------------------
# PRICE MAP (Stripe Price IDs → Plan + Credits)
# -----------------------------
PRICE_MAP = {
    "price_1ThsIOPE4wCsfg73Om6UdO0C": ("pro", 150),
    "price_1TI27QPE4wCsfg73kGgLgKI4": ("business", 500),
    "price_1TGwAJPE4wCsfg73gMQlv8Ph": ("premium", 999999),
}

# -----------------------------
# ROOT
# -----------------------------
@app.get("/")
def root():
    return {"status": "billing service running"}

# -----------------------------
# IDEMPOTENCY (avoid double charges)
# -----------------------------
def already_processed(event_id: str) -> bool:
    doc = db.collection("stripe_events").document(event_id).get()
    return doc.exists

def mark_processed(event_id: str):
    db.collection("stripe_events").document(event_id).set({
        "processed": True
    })

# -----------------------------
# USER HELPERS
# -----------------------------
def get_user_ref(email: str):
    docs = db.collection("users").where("email", "==", email).stream()
    for d in docs:
        return d.reference
    return None

def set_user(email: str, data: dict):
    ref = get_user_ref(email)
    if not ref:
        ref = db.collection("users").document()

    ref.set({
        "email": email,
        **data
    }, merge=True)

def add_credits(email: str, credits: int):
    ref = get_user_ref(email)
    if not ref:
        ref = db.collection("users").document()

    ref.set({
        "email": email,
        "credits": firestore.Increment(credits)
    }, merge=True)

# -----------------------------
# EMAIL RESOLVER
# -----------------------------
def get_email(session):
    email = session.get("customer_details", {}).get("email")

    if email:
        return email

    customer_id = session.get("customer")
    if customer_id:
        customer = stripe.Customer.retrieve(customer_id)
        return customer.get("email")

    return None

# -----------------------------
# WEBHOOK
# -----------------------------
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

    event_id = event["id"]

    # prevent duplicate processing
    if already_processed(event_id):
        return {"status": "already processed"}

    event_type = event["type"]

    # -----------------------------
    # CHECKOUT COMPLETE
    # -----------------------------
    if event_type == "checkout.session.completed":

        session = event["data"]["object"]
        email = get_email(session)

        price_id = session.get("metadata", {}).get("price_id")

        if price_id in PRICE_MAP:
            plan, credits = PRICE_MAP[price_id]

            if email:
                set_user(email, {
                    "plan": plan
                })

                if credits > 0 and plan != "premium":
                    add_credits(email, credits)

                mark_processed(event_id)

                print("🔥 PAYMENT SUCCESS:", email, plan, credits)

    # -----------------------------
    # RENEWALS
    # -----------------------------
    elif event_type == "invoice.paid":

        invoice = event["data"]["object"]

        customer = stripe.Customer.retrieve(invoice["customer"])
        email = customer.get("email")

        plan = invoice.get("metadata", {}).get("plan")

        if email and plan:
            set_user(email, {"plan": plan})

            if plan != "premium":
                add_credits(email, PRICE_MAP.get(plan, ("", 0))[1])

            mark_processed(event_id)

            print("💰 RENEWAL:", email, plan)

    # -----------------------------
    # CANCELLATION
    # -----------------------------
    elif event_type == "customer.subscription.deleted":

        sub = event["data"]["object"]
        customer = stripe.Customer.retrieve(sub["customer"])
        email = customer.get("email")

        if email:
            set_user(email, {"plan": "free"})
            mark_processed(event_id)

            print("❌ CANCELLED:", email)

    return {"ok": True}
