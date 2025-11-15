import os
import logging
from flask import Flask, request, jsonify
from functools import wraps
from billing_manager import BillingManager

# Setup Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- INTERNAL SERVICE TOKEN ---
INTERNAL_TOKEN = os.getenv("INTERNAL_SERVICE_TOKEN", None)

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('FLASK_SECRET_KEY', 'billing-dev-key')

# Initialize the Business Logic
manager = BillingManager()

# --- DECORATOR: Require Internal Service Token ---
def require_internal_token(f):
    """
    Decorator to protect internal service endpoints.
    Checks X-INTERNAL-TOKEN header against INTERNAL_SERVICE_TOKEN env var.
    In dev mode (no token configured), allows all requests.
    """
    @wraps(f)
    def decorated(*args, **kwargs):
        if INTERNAL_TOKEN is None:
            # Dev mode: allow if not configured
            return f(*args, **kwargs)
        token = request.headers.get("X-INTERNAL-TOKEN")
        if not token or token != INTERNAL_TOKEN:
            logger.warning(f"Unauthorized internal request: missing or invalid token")
            return jsonify({"error": "Forbidden"}), 403
        return f(*args, **kwargs)
    return decorated

# --- Internal Admin Endpoints ---
# Protected by X-INTERNAL-TOKEN header when INTERNAL_SERVICE_TOKEN is configured

@app.route('/account', methods=['POST'])
def create_account():
    """
    Creates a new user record.
    Called by the Auth Server upon user registration.
    """
    data = request.get_json()
    user_id = data.get('user_id')
    tier = data.get('tier', 'guest')
    
    if not user_id:
        return jsonify({"error": "user_id is required"}), 400

    # Business Logic: Define starting balances for tiers
    # Guests get nothing. Pro users might get a starting grant.
    initial_balance = 0.00
    if tier == 'admin': # 'admin' here refers to the Project Owner/Subscriber role
        initial_balance = 5.00 # Example starting grant
        
    success = manager.create_account(user_id, tier, initial_balance)
    
    if success:
        return jsonify({"status": "created", "user_id": user_id, "balance": initial_balance}), 201
    else:
        # Not strictly an error if it exists, but good to know
        return jsonify({"status": "exists", "message": "Account already exists"}), 200

@app.route('/balance/<user_id>', methods=['GET'])
def get_balance(user_id):
    """
    Returns the current balance and tier.
    Called by the Backend 'Governor' before running expensive models.
    """
    account = manager.get_account(user_id)
    if not account:
        return jsonify({"error": "Account not found"}), 404
    
    # Return simplified status for the Governor
    return jsonify({
        "user_id": account['user_id'],
        "tier": account['tier'],
        "balance": account['balance'],
        "currency": "USD"
    })

@app.route('/deduct', methods=['POST'])
def deduct_funds():
    """
    Deducts funds for API usage.
    Called by the Backend after an LLM call completes.
    """
    data = request.get_json()
    user_id = data.get('user_id')
    cost = data.get('cost')
    description = data.get('description', 'API Usage')
    job_id = data.get('job_id') # Optional

    if not user_id or cost is None:
        return jsonify({"error": "user_id and cost are required"}), 400

    try:
        cost_float = float(cost)
        success = manager.deduct_funds(user_id, cost_float, description, job_id)
        
        if success:
            return jsonify({"status": "success", "message": "Funds deducted"}), 200
        else:
            # 402 Payment Required is the correct HTTP code for "Not enough money"
            return jsonify({"status": "failed", "message": "Insufficient funds"}), 402
            
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        logger.error(f"Deduct failed: {e}")
        return jsonify({"error": "Internal server error"}), 500

@app.route('/top_up', methods=['POST'])
def top_up():
    """
    Adds funds to a user's account.
    Called by the Stripe Webhook Handler (future) or Admin Dashboard.
    """
    data = request.get_json()
    user_id = data.get('user_id')
    amount = data.get('amount')
    description = data.get('description', 'Manual Top-up')

    if not user_id or amount is None:
        return jsonify({"error": "user_id and amount are required"}), 400

    try:
        amount_float = float(amount)
        success = manager.add_funds(user_id, amount_float, description)
        
        if success:
            return jsonify({"status": "success", "message": f"Added ${amount_float:.2f}"}), 200
        else:
            return jsonify({"error": "Failed to add funds"}), 500
            
    except ValueError:
        return jsonify({"error": "Invalid amount format"}), 400

if __name__ == '__main__':
    print("--- Billing Server (The Bank) ---")
    print("Running on http://localhost:5004")
    app.run(debug=True, port=5004)