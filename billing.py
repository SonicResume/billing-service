from firebase_admin import firestore


# NOAH Language subscription credits
PLAN_CREDITS = {
    "pro": 150,
    "business": 500,
    "premium": 999999,  # unlimited-style access
}


def apply_plan(db, email: str, plan: str) -> bool:
    """
    Upgrade user plan after successful Stripe payment.

    Args:
        db: Firebase Firestore instance
        email: User email from Stripe checkout
        plan: Stripe metadata plan name

    Returns:
        True if user updated successfully
        False if user not found or plan invalid
    """

    if not email:
        print("❌ Missing user email")
        return False

    plan = plan.lower().strip()

    credits = PLAN_CREDITS.get(plan)

    if credits is None:
        print("❌ Unknown plan:", plan)
        return False

    try:
        users = db.collection("users")

        docs = users.where(
            filter=firestore.FieldFilter(
                "email",
                "==",
                email
            )
        ).stream()

        for doc in docs:
            doc.reference.update({
                "plan": plan,
                "credits": credits,
                "subscriptionStatus": "active",
                "updatedAt": firestore.SERVER_TIMESTAMP
            })

            print("✅ PAYMENT APPLIED")
            print("User:", email)
            print("Plan:", plan)
            print("Credits:", credits)

            return True

        print("❌ Firebase user not found:", email)
        return False

    except Exception as e:
        print("❌ Firebase billing update failed:", str(e))
        return False
