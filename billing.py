

from fastapi import FastAPI, Request, HTTPException
import stripe, os, json, logging
import firebase_admin
from firebase_admin import credentials, firestore
from dotenv import load_dotenv

load_dotenv()
logging.basicConfig(level=logging.INFO)
app = FastAPI()

stripe.api_key = os.getenv("STRIPE_SECRET_KEY")
WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET")

firebase_key = os.environ["FIREBASE_SERVICE_ACCOUNT"]
cred = credentials.Certificate(json.loads(firebase_key))
if not firebase_admin._apps:
    firebase_admin.initialize_app(cred)
db = firestore.client()

PRICE_MAP = {
    "price_1ThsIOPE4wCsfg73Om6UdO0C":{"plan":"pro","credits":150},
    "price_1TI27QPE4wCsfg73kGgLgKI4":{"plan":"business","credits":500},
    "price_1TGwAJPE4wCsfg73gMQlv8Ph":{"plan":"premium","credits":999999},
}

@app.get("/")
def root(): return {"status":"billing service running"}

def user_ref(email): return db.collection("users").document(email.lower())

def update_user(email, **fields):
    user_ref(email).set({"email":email, **fields}, merge=True)

@app.post("/create-checkout")
async def create_checkout(req: Request):
    data = await req.json()
    email = data.get("email")
    price_id = data.get("price_id")
    if not email or price_id not in PRICE_MAP:
        raise HTTPException(400,"Invalid request")
    session = stripe.checkout.Session.create(
        mode="subscription",
        payment_method_types=["card"],
        line_items=[{"price":price_id,"quantity":1}],
        customer_email=email,
        success_url="https://noah-language.vercel.app/success?session_id={CHECKOUT_SESSION_ID}",
        cancel_url="https://noah-language.vercel.app/pricing",
    )
    return {"url":session.url}

@app.post("/stripe-webhook")
async def webhook(request: Request):
    payload = await request.body()
    sig = request.headers.get("stripe-signature")
    try:
        event = stripe.Webhook.construct_event(payload,sig,WEBHOOK_SECRET)
    except ValueError:
        raise HTTPException(400,"Invalid payload")
    except stripe.error.SignatureVerificationError:
        raise HTTPException(400,"Invalid signature")

    eid = event["id"]
    eref = db.collection("stripe_events").document(eid)
    if eref.get().exists:
        return {"status":"duplicate"}
    etype = event["type"]

    if etype in ("checkout.session.completed","invoice.paid"):
        obj = event["data"]["object"]
        sub_id = obj.get("subscription")
        if not sub_id:
            return {"ok":True}
        sub = stripe.Subscription.retrieve(sub_id)
        customer = stripe.Customer.retrieve(sub["customer"])
        email = customer["email"]
        price_id = sub["items"]["data"][0]["price"]["id"]
        plan = PRICE_MAP[price_id]["plan"]
        credits = PRICE_MAP[price_id]["credits"]
        update_user(email,
                    plan=plan,
                    customer_id=sub["customer"],
                    subscription_id=sub_id,
                    price_id=price_id,
                    credits=firestore.Increment(credits))
        eref.set({"done":True})

    elif etype=="customer.subscription.deleted":
        sub = event["data"]["object"]
        customer = stripe.Customer.retrieve(sub["customer"])
        update_user(customer["email"], plan="free")
        eref.set({"done":True})

    return {"ok":True}

@app.get("/user/{email}")
def get_user(email:str):
    doc = user_ref(email).get()
    return doc.to_dict() if doc.exists else {"email":email,"plan":"free","credits":0}

@app.get("/api/health")
def health():
    return {"status":"ok","service":"billing-service"}
