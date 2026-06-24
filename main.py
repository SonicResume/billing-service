from fastapi import FastAPI, Request, HTTPException
import stripe
import os

import firebase_admin
from firebase_admin import credentials, firestore
from dotenv import load_dotenv

# -----------------------------
# INIT
# -----------------------------
load_dotenv()

app = FastAPI()

stripe.api_key = os.getenv("STRIPE_SECRET_KEY")
WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET")

# -----------------------------
# FIREBASE INIT (RENDER SAFE)
# -----------------------------
FIREBASE_FILE = "serviceAccountKey.json"

if not firebase_admin._apps:
    if not os.path.exists(FIREBASE_FILE):
        raise Exception("Missing Firebase serviceAccountKey.json on server")

    cred = credentials.Certificate(FIREBASE_FILE)
    firebase_admin.initialize_app(cred)

db = firestore.client()

# -----------------------------
# PRICE MAP
# -----------------------------
PRICE_MAP = {
    "price_1ThsIOPE4wCsfg73Om6UdO0C": ("pro", 150),
    "price_1TI27QPE4wCsfg73kGgLgKI4": ("business", 500),
    "price_1TGwAJPE4wCsfg73gMQlv8Ph": ("premium", 999999),
}

# -----------------------------
# ROOT CHECK
# -----------------------------
@app.get("/")
def root():
    return {"status": "billing service running"}

# -----------------------------
# HELPERS
# -----------------------------
def already_processed(event_id: str):
    doc = db.collection("stripe_events").document(event_id).get()
    return doc.exists


def mark_processed(event_id: str):
    db.collection("stripe_events").document(event_id).set({"processed": True})


def get_user_ref(email: str):
    docs = db.collection("users").where("email", "==", email).stream()
    for d in docs:
        return d.reference
    return db.collection("users").document()


def set_plan(email: str, plan: str):
    ref = get_user_ref(email)
    ref.set({"email": email, "plan": plan}, merge=True)


def add_credits(email: str, credits: int):
    ref = get_user_ref(email)
    ref.set({"email": email, "credits": firestore.Increment(credits)}, merge=True)

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

    if already_processed(event_id):
        return {"status": "already processed"}

    event_type = event["type"]

    # -------------------------
    # CHECKOUT COMPLETE
    # -------------------------
    if event_type == "checkout.session.completed":

        session = event["data"]["object"]

        email = (
            session.get("customer_details", {}).get("email")
            or session.get("customer_email")
        )

        price_id = session.get("metadata", {}).get("price_id")

        if email and price_id in PRICE_MAP:
            plan, credits = PRICE_MAP[price_id]

            set_plan(email, plan)

            if plan != "premium":
                add_credits(email, credits)

            mark_processed(event_id)

    # -------------------------
    # SUBSCRIPTION RENEWAL
    # -------------------------
    elif event_type == "invoice.paid":

        invoice = event["data"]["object"]

        customer = stripe.Customer.retrieve(invoice["customer"])
        email = customer.get("email")

        plan = invoice.get("metadata", {}).get("plan")

        if email and plan:
            set_plan(email, plan)
            mark_processed(event_id)

    # -------------------------
    # CANCEL
    # -------------------------
    elif event_type == "customer.subscription.deleted":

        sub = event["data"]["object"]
        customer = stripe.Customer.retrieve(sub["customer"])
        email = customer.get("email")

        if email:
            set_plan(email, "free")
            mark_processed(event_id)

    return {"ok": True}
