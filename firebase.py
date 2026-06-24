import os
import json
import base64
import firebase_admin
from firebase_admin import credentials, firestore

firebase_b64 = os.getenv("FIREBASE_KEY_B64")

if not firebase_b64:
    raise Exception("FIREBASE_KEY_B64 missing")

firebase_json = json.loads(base64.b64decode(firebase_b64))

cred = credentials.Certificate(firebase_json)

if not firebase_admin._apps:
    firebase_admin.initialize_app(cred)

db = firestore.client()
