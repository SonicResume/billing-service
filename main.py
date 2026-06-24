from fastapi import FastAPI, Request, HTTPException
import stripe
import os
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
# FIREBASE INIT
# -----------------------------
cred = credentials.Certificate("serviceAccountKey.json")
firebase_admin.initialize_app(cred)

if not firebase_admin._apps:
    firebase_admin.initialize_app(cred)

db = firestore.client()

# -----------------------------
# PRICE → PLAN MAP (SOURCE OF TRUTH)
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
# IDEMPOTENCY
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

def add_credits(email: str, credits: int):
    ref = get_user_ref(email)
    if not ref:
        ref = db.collection("users").document()

    ref.set({
        "email": email,
        "credits": firestore.Increment(credits)
    }, merge=True)

def set_plan(email: str, plan: str):
    ref = get_user_ref(email)
    if not ref:
        ref = db.collection("users").document()

    ref.set({
        "email": email,
        "plan": plan
    }, merge=True)

# -----------------------------
# EMAIL RESOLVER
# -----------------------------
def get_email_from_session(session):
    email = session.get("customer_details", {}).get("email")

    if email:
        return email

    # fallback
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

    # prevent duplicates
    if already_processed(event_id):
        return {"status": "already processed"}

    event_type = event["type"]

    # -----------------------------
    # CHECKOUT COMPLETE
    # -----------------------------
    if event_type == "checkout.session.completed":

        session = event["data"]["object"]

        email = get_email_from_session(session)

        # SAFE: derive from PRICE, not metadata
        line_items = session.get("display_items", []) or session.get("line_items")

        price_id = None
        try:
            price_id = session["metadata"]["price_id"]
        except:
            pass

        plan = None
        credits = 0

        if price_id in PRICE_MAP:
            plan, credits = PRICE_MAP[price_id]

        if email and plan:
            set_plan(email, plan)

            if credits > 0 and plan != "premium":
                add_credits(email, credits)

            mark_processed(event_id)

            print("🔥 PAYMENT SUCCESS:", email, plan, credits)

    # -----------------------------
    # SUBSCRIPTION RENEWAL
    # -----------------------------
    elif event_type == "invoice.paid":

        invoice = event["data"]["object"]

        customer = stripe.Customer.retrieve(invoice["customer"])
        email = customer.get("email")

        plan = invoice.get("metadata", {}).get("plan")

        if email and plan:
            set_plan(email, plan)

            if plan != "premium":
                add_credits(email, PRICE_MAP.get(plan, ("", 0))[1])

            mark_processed(event_id)

            print("💰 RENEWAL:", email, plan)

    # -----------------------------
    # CANCELLED
    # -----------------------------
    elif event_type == "customer.subscription.deleted":

        sub = event["data"]["object"]
        customer = stripe.Customer.retrieve(sub["customer"])
        email = customer.get("email")

        if email:
            set_plan(email, "free")
            mark_processed(event_id)

            print("❌ CANCELLED:", email)

    return {"ok": True}
