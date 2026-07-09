from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import stripe
import os
import json

import firebase_admin
from firebase_admin import credentials, firestore
from dotenv import load_dotenv


# -----------------------------
# INIT
# -----------------------------
load_dotenv()

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

stripe.api_key = os.getenv("STRIPE_SECRET_KEY")
WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET")


# -----------------------------
# FIREBASE INIT
# -----------------------------
firebase_key = os.getenv("FIREBASE_SERVICE_ACCOUNT")

if not firebase_key:
    raise RuntimeError(
        "Missing FIREBASE_SERVICE_ACCOUNT environment variable"
    )

try:
    firebase_credentials = json.loads(firebase_key)
except json.JSONDecodeError:
    raise RuntimeError(
        "FIREBASE_SERVICE_ACCOUNT must be valid JSON"
    )


if not firebase_admin._apps:
    cred = credentials.Certificate(firebase_credentials)
    firebase_admin.initialize_app(cred)


db = firestore.client()


# -----------------------------
# PLANS
# -----------------------------
PRICE_MAP = {

    "price_1TbF9BPE4wCsfg732ScUJfmc": {
        "plan": "pro",
        "credits": 150
    },

    "price_1TnzrFPE4wCsfg73xSOMZNuH": {
        "plan": "business",
        "credits": 500
    },

    "price_1TGwAJPE4wCsfg73gMQlv8Ph": {
        "plan": "premium",
        "credits": 999999
    }
}


# -----------------------------
# HEALTH
# -----------------------------
@app.get("/")
def root():
    return {
        "status": "billing service running"
    }


@app.get("/api/health")
def health():
    return {
        "status": "ok",
        "service": "billing-service"
    }


# -----------------------------
# PRICES
# -----------------------------
@app.get("/prices")
def prices():
    return PRICE_MAP


# -----------------------------
# FIRESTORE HELPERS
# -----------------------------
def get_user_ref(email):

    users = (
        db.collection("users")
        .where("email", "==", email)
        .stream()
    )

    for user in users:
        return user.reference

    return db.collection("users").document()


def update_user_plan(email, plan, credits):

    ref = get_user_ref(email)

    ref.set(
        {
            "email": email,
            "plan": plan,
            "credits": credits,
            "updatedAt": firestore.SERVER_TIMESTAMP
        },
        merge=True
    )


def event_exists(event_id):

    return (
        db.collection("stripe_events")
        .document(event_id)
        .get()
        .exists
    )


def save_event(event_id):

    db.collection("stripe_events").document(event_id).set(
        {
            "done": True,
            "createdAt": firestore.SERVER_TIMESTAMP
        }
    )

# -----------------------------
# STRIPE WEBHOOK
# -----------------------------
@app.post("/stripe-webhook")
async def stripe_webhook(request: Request):

    payload = await request.body()
    signature = request.headers.get("stripe-signature")

    try:
        event = stripe.Webhook.construct_event(
            payload,
            signature,
            WEBHOOK_SECRET
        )

    except Exception as e:
        raise HTTPException(
            status_code=400,
            detail=str(e)
        )


    event_id = event.id


    if event_exists(event_id):
        return {
            "status": "duplicate"
        }


    if event.type == "checkout.session.completed":

        session = event.data.object


        email = None

        if session.customer_details:
            email = session.customer_details.email

        if not email:
            email = session.customer_email


        metadata = session.metadata or {}

        price_id = metadata.get("price_id")


        if email and price_id in PRICE_MAP:

            plan_data = PRICE_MAP[price_id]


            update_user_plan(
                email,
                plan_data["plan"],
                plan_data["credits"]
            )


    save_event(event_id)


    return {
        "ok": True
    }
# -----------------------------
# CREATE CHECKOUT
# -----------------------------
@app.post("/create-checkout")
async def create_checkout(request: Request):


    data = await request.json()


    price_id = data.get(
        "price_id"
    )

    email = data.get(
        "email"
    )


    if not price_id or not email:

        raise HTTPException(
            status_code=400,
            detail="missing data"
        )


    if price_id not in PRICE_MAP:

        raise HTTPException(
            status_code=400,
            detail="invalid price"
        )


    session = stripe.checkout.Session.create(

        mode="subscription",

        payment_method_types=[
            "card"
        ],

        line_items=[
            {
                "price": price_id,
                "quantity": 1
            }
        ],

        customer_email=email,

        metadata={
            "price_id": price_id,
            "plan": PRICE_MAP[price_id]["plan"]
        },


        success_url=
        "https://noah-language.vercel.app/success",

        cancel_url=
        "https://noah-language.vercel.app/pricing"

    )


    return {
        "url": session.url
    }


# -----------------------------
# CREATE CHECKOUT SESSION
# -----------------------------
@app.post("/")
async def create_checkout(request: Request):

    data = await request.json()

    price_id = data.get("price_id")
    email = data.get("email")

    if not price_id:
        raise HTTPException(
            status_code=400,
            detail="Missing price_id"
        )

    if price_id not in PRICE_MAP:
        raise HTTPException(
            status_code=400,
            detail="Invalid price"
        )

    try:

        session = stripe.checkout.Session.create(
            mode="subscription",
            customer_email=email,
            line_items=[
                {
                    "price": price_id,
                    "quantity": 1,
                }
            ],
            success_url="https://noah-language.vercel.app/success",
            cancel_url="https://noah-language.vercel.app/pricing",
            metadata={
                "plan": PRICE_MAP[price_id]["plan"],
                "email": email
            }
        )

        return {
            "url": session.url
        }

    except Exception as e:

        raise HTTPException(
            status_code=500,
            detail=str(e)
        )

# -----------------------------
# USER STATUS
# -----------------------------
@app.get("/user/{email}")
def user_status(email: str):


    users = (
        db.collection("users")
        .where("email", "==", email)
        .stream()
    )


    for user in users:

        return user.to_dict()


    return {

        "email": email,

        "plan": "free",

        "credits": 0

    }
