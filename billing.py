from firebase_admin import firestore


# NOAH Language subscription credits
PLAN_CREDITS = {
    "pro": 150,
    "business": 500,
    "premium": 999999,  # unlimited-style access
}


def apply_plan(db, email: str, plan: str):
    """
    Upgrade user plan after successful Stripe payment.

    Args:
        db: Firebase Firestore instance
        email: User email from Stripe checkout
        plan: Stripe metadata plan name

    Returns:
        True if user updated
        False if user not found
    """

    users = db.collection("users")

    docs = users.where(
        "email",
        "==",
        email
    ).stream()

    for doc in docs:
        credits = PLAN_CREDITS.get(plan)

        if credits is None:
            print("❌ Unknown plan:", plan)
            return False

        doc.reference.update({
            "plan": plan,
            "credits": credits,
            "updatedAt": firestore.SERVER_TIMESTAMP
        })

        print("✅ PAYMENT APPLIED")
        print("User:", email)
        print("Plan:", plan)
        print("Credits:", credits)

        return True

    print("❌ Firebase user not found:", email)

    return False
