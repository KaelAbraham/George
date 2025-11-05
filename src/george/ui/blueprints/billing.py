from flask import Blueprint, render_template, request
from ..auth.auth_client import verify_firebase_token
import logging

logger = logging.getLogger(__name__)

billing_bp = Blueprint('billing', __name__, url_prefix='/account')

@billing_bp.route('/billing')
@verify_firebase_token()
def billing_page():
    """
    Displays the user's subscription and credit information.
    The customer profile is attached to `request.user` by the decorator.
    """
    # request.user now contains the customer profile from Firestore
    # request.user_auth contains the raw auth token info
    customer_profile = request.user 
    auth_info = request.user_auth
    
    logger.info(f"Displaying billing page for user: {customer_profile.get('email')}")
    
    return render_template('billing.html', user_auth=auth_info, customer=customer_profile)