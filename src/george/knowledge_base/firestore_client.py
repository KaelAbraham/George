import firebase_admin
from firebase_admin import credentials, firestore
from pathlib import Path

# Path to your downloaded service account key
PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
CREDENTIALS_PATH = PROJECT_ROOT / "george-6a8da-firebase-adminsdk-fbsvc-e85c43d430.json"

# Initialize the app with a service account, granting admin privileges
cred = credentials.Certificate(str(CREDENTIALS_PATH))
firebase_admin.initialize_app(cred)

# Get a client to interact with the database
db = firestore.client()

print("Successfully connected to Firestore!")

# --- Example: Add some data ---
doc_ref = db.collection('users').document('alovelace')
doc_ref.set({
    'first': 'Ada',
    'last': 'Lovelace',
    'born': 1815
})
print("Data added to the 'users' collection.")