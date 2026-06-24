def get_user(db, email: str):
    docs = db.collection("users").where("email", "==", email).stream()

    for doc in docs:
        return doc.id, doc.to_dict()

    return None, None
