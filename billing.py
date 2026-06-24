from firebase_admin import firestore

PLAN_CREDITS = {
    "pro": 150,
    "business": 500,
    "premium": 999999,
}

def apply_plan(db, email: str, plan: str):
    users = db.collection("users")

    docs = users.where("email", "==", email).stream()

    for doc in docs:
        doc.reference.update({
            "plan": plan,
            "credits": firestore.Increment(PLAN_CREDITS.get(plan, 0))
        })
        return True

    return False
