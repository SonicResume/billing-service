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

cred = credentials.Certificate("serviceAccountKey.json")

if not firebase_admin._apps:
    firebase_admin.initialize_app(cred)

db = firestore.client()

# -----------------------------
# PLAN SYSTEM (UNIFIED)
# -----------------------------
PRICE_MAP = {
    "price_1ThsIOPE4wCsfg73Om6UdO0C": {
        "plan": "pro",
        "credits": 150
    },
    "price_1TI27QPE4wCsfg73kGgLgKI4": {
        "plan": "business",
        "credits": 500
    },
    "price_1TGwAJPE4wCsfg73gMQlv8Ph": {
        "plan": "premium",
        "credits": 999999
    }
}
# -----------------------------
# HEALTH CHECK
# -----------------------------
@app.get("/")
def root():
    return {"status": "billing service running"}

# -----------------------------
# PRICES (ALL APPS USE THIS)
# -----------------------------
@app.get("/prices")
def get_prices():
    return PRICE_MAP

# -----------------------------
# USER HELPERS
# -----------------------------
def get_user_ref(email: str):
    docs = db.collection("users").where("email", "==", email).stream()

    for doc in docs:
        return doc.reference

    return db.collection("users").document()

def set_plan(email: str, plan: str):
    ref = get_user_ref(email)
    ref.set({"email": email, "plan": plan}, merge=True)

def add_credits(email: str, credits: int):
    ref = get_user_ref(email)
    ref.set({
        "email": email,
        "credits": firestore.Increment(credits)
    }, merge=True)

def mark_event(event_id: str):
    db.collection("stripe_events").document(event_id).set({"done": True})

def event_done(event_id: str):
    return db.collection("stripe_events").document(event_id).get().exists

# -----------------------------
# STRIPE WEBHOOK (UNIFIED CORE)
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

    if event_done(event_id):
        return {"status": "duplicate ignored"}

    event_type = event["type"]

    # -------------------------
    # PAYMENT COMPLETED
    # -------------------------
    if event_type == "checkout.session.completed":

        session = event["data"]["object"]

        email = (
            session.get("customer_details", {}).get("email")
            or session.get("customer_email")
        )

        metadata = session.get("metadata") or {}
        price_id = metadata.get("price_id")

        if not email or not price_id:
            return {"error": "missing data"}

        if price_id not in PRICE_MAP:
            return {"error": "invalid price_id"}

        plan_data = PRICE_MAP[price_id]
        plan = plan_data["plan"]
        credits = plan_data["credits"]

        set_plan(email, plan)

        if credits > 0:
            add_credits(email, credits)

        mark_event(event_id)

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
            mark_event(event_id)

    # -------------------------
    # CANCEL SUBSCRIPTION
    # -------------------------
    elif event_type == "customer.subscription.deleted":

        sub = event["data"]["object"]

        customer = stripe.Customer.retrieve(sub["customer"])
        email = customer.get("email")

        if email:
            set_plan(email, "free")
            mark_event(event_id)

    return {"ok": True}

# -----------------------------
# CHECKOUT (USED BY ALL APPS)
# -----------------------------
@app.post("/create-checkout")
async def create_checkout(request: Request):

    data = await request.json()

    price_id = data.get("price_id")
    email = data.get("email")

    if not price_id or not email:
        raise HTTPException(status_code=400, detail="missing data")

    session = stripe.checkout.Session.create(
        mode="payment",
        payment_method_types=["card"],
        line_items=[{
            "price": price_id,
            "quantity": 1
        }],
        success_url="https://noah-language.vercel.app/success?session_id={CHECKOUT_SESSION_ID}",
        cancel_url="https://noah-language.vercel.app/pricing",
        customer_email=email,
        metadata={"price_id": price_id}
    )

    return {"url": session.url}

# -----------------------------
# USER STATUS (USED BY ALL APPS)
# -----------------------------
@app.get("/user/{email}")
def get_user_status(email: str):

    docs = db.collection("users").where("email", "==", email).stream()

    for doc in docs:
        return doc.to_dict()

    return {
        "email": email,
        "plan": "free",
        "credits": 0
    }

@app.get("/api/health")
def health():
    return {
        "status": "ok",
        "service": "billing-service"
    }
