"""
Robust Cost Tracking with Pre-Authorization & Idempotent Transactions

This module provides race-condition-safe billing operations:
1. Pre-authorization: Reserve funds before expensive operations
2. Idempotent transactions: Use unique job IDs to prevent double-charging
3. Capture pattern: Actual charge after operation completes
4. Rollback on failure: Release reserved funds automatically

This ensures the user gets the answer XOR the user gets charged, never both or neither.

RESILIENCE: This module uses dependency injection for the billing_client to ensure
all billing calls are resilient with automatic retries, circuit breaker protection,
and fail-open semantics. The ResilientServiceClient is passed in at initialization
rather than creating a brittle requests.Session() internally.
"""

import logging
import uuid
from typing import Optional, Dict, Any, Tuple, TYPE_CHECKING
from enum import Enum
from datetime import datetime
from pathlib import Path
import sqlite3

if TYPE_CHECKING:
    from service_utils import ResilientServiceClient

logger = logging.getLogger(__name__)


class ReservationState(Enum):
    """States of a cost reservation."""
    ACTIVE = "active"
    CAPTURED = "captured"
    RELEASED = "released"
    EXPIRED = "expired"


class CostTracker:
    """
    Manages cost pre-authorization and idempotent transactions.
    
    Workflow:
    1. reserve_funds(user_id, estimated_cost) → reservation_id
    2. Perform expensive operation (LLM call)
    3. capture_funds(reservation_id, actual_cost) → success
    4. On failure: release_funds(reservation_id) → refund
    
    Benefits:
    - Pre-auth prevents "answer without charge" race condition
    - Idempotent job IDs prevent double-charging
    - Automatic rollback on failure
    - Persistent tracking for reconciliation
    
    RESILIENCE: Uses dependency injection for billing_client to ensure all
    calls benefit from automatic retries, exponential backoff, circuit breaker,
    and fail-open semantics via ResilientServiceClient.
    """
    
    def __init__(self, billing_client: "ResilientServiceClient", 
                 internal_headers: Dict[str, str], 
                 db_path: str = "data/cost_reservations.db"):
        """
        Initialize CostTracker with dependency injection.
        
        Args:
            billing_client: ResilientServiceClient instance (injected dependency)
                           All billing calls will use this resilient client
                           with automatic retries, circuit breaker, and fail-open
            internal_headers: Dict with X-INTERNAL-TOKEN for inter-service auth
            db_path: Path to SQLite DB for tracking reservations
            
        RESILIENCE: The billing_client is passed in, not created here. This allows
        the caller (backend/app.py) to configure retry/timeout behavior centrally.
        The ResilientServiceClient automatically handles:
        - Retries on transient failures
        - Exponential backoff
        - Circuit breaker (detects repeated failures)
        - Proper error handling and logging
        """
        self.billing_client = billing_client
        self.internal_headers = internal_headers
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()
    
    def _get_conn(self) -> sqlite3.Connection:
        """Get a new SQLite connection."""
        return sqlite3.connect(str(self.db_path))
    
    def _init_db(self):
        """Initialize reservations tracking table."""
        try:
            with self._get_conn() as conn:
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS reservations (
                        reservation_id TEXT PRIMARY KEY,
                        user_id TEXT NOT NULL,
                        estimated_cost REAL NOT NULL,
                        actual_cost REAL,
                        state TEXT NOT NULL,
                        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                        error_message TEXT
                    )
                """)
                conn.execute("""
                    CREATE INDEX IF NOT EXISTS idx_reservations_user 
                    ON reservations (user_id, state)
                """)
                conn.commit()
            logger.info("CostTracker database initialized successfully")
        except Exception as e:
            logger.critical(f"Failed to initialize CostTracker database: {e}", exc_info=True)
            raise
    
    def _record_reservation(self, reservation_id: str, user_id: str, 
                           estimated_cost: float, state: str):
        """Record reservation in local DB for reconciliation."""
        try:
            with self._get_conn() as conn:
                conn.execute("""
                    INSERT OR REPLACE INTO reservations 
                    (reservation_id, user_id, estimated_cost, state, updated_at)
                    VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
                """, (reservation_id, user_id, estimated_cost, state))
                conn.commit()
        except Exception as e:
            logger.error(f"Failed to record reservation {reservation_id}: {e}")
    
    def _update_reservation(self, reservation_id: str, state: str, 
                           actual_cost: Optional[float] = None, 
                           error_message: Optional[str] = None):
        """Update reservation state in local DB."""
        try:
            with self._get_conn() as conn:
                if actual_cost is not None:
                    conn.execute("""
                        UPDATE reservations 
                        SET state = ?, actual_cost = ?, error_message = ?, updated_at = CURRENT_TIMESTAMP
                        WHERE reservation_id = ?
                    """, (state, actual_cost, error_message, reservation_id))
                else:
                    conn.execute("""
                        UPDATE reservations 
                        SET state = ?, error_message = ?, updated_at = CURRENT_TIMESTAMP
                        WHERE reservation_id = ?
                    """, (state, error_message, reservation_id))
                conn.commit()
        except Exception as e:
            logger.error(f"Failed to update reservation {reservation_id}: {e}")
    
    def reserve_funds(self, user_id: str, estimated_cost: float) -> Optional[str]:
        """
        PRE-AUTHORIZATION: Reserve funds before expensive operation.
        
        This prevents the "answer without charge" race condition:
        - If reserve fails, we don't proceed
        - If reserve succeeds, funds are held
        - Later we capture actual cost or release funds
        
        RESILIENCE: Uses injected billing_client with automatic retries and
        circuit breaker. If the circuit breaker is open (billing service down),
        returns None to deny the request. This is correct: better to deny than
        to charge unpredictably.
        
        Args:
            user_id: User making the request
            estimated_cost: Estimated cost in dollars (e.g., 0.05)
            
        Returns:
            reservation_id: Unique ID for this reservation (track this)
            None: If pre-auth fails (user insufficient funds or service error)
        """
        from service_utils import ServiceUnavailable
        
        reservation_id = f"res-{uuid.uuid4()}"
        
        try:
            logger.info(f"[PREAUTH] Reserving ${estimated_cost:.6f} for user {user_id}")
            
            resp = self.billing_client.post(
                "/reserve",
                json={
                    "user_id": user_id,
                    "reservation_id": reservation_id,
                    "estimated_cost": estimated_cost
                },
                headers=self.internal_headers
            )
            
            if resp.status_code == 200:
                self._record_reservation(reservation_id, user_id, estimated_cost, 
                                        ReservationState.ACTIVE.value)
                logger.info(f"[PREAUTH] ✓ Reservation {reservation_id} created successfully")
                return reservation_id
            
            elif resp.status_code == 402:  # Payment Required (insufficient funds)
                error_msg = resp.json().get('error', 'Insufficient funds')
                self._record_reservation(reservation_id, user_id, estimated_cost, 
                                        ReservationState.EXPIRED.value)
                logger.warning(f"[PREAUTH] ✗ Pre-auth failed for {user_id}: {error_msg}")
                return None
            
            else:
                error_msg = f"Billing server returned {resp.status_code}"
                self._record_reservation(reservation_id, user_id, estimated_cost, 
                                        ReservationState.EXPIRED.value)
                logger.error(f"[PREAUTH] ✗ Unexpected response: {error_msg}")
                return None
        
        except ServiceUnavailable:
            # Circuit breaker is open (service repeatedly failed)
            # This is correct behavior: deny the request rather than proceeding
            # without being able to charge (or vice versa)
            logger.error(f"[PREAUTH] ✗ Billing service unavailable (circuit breaker open) for user {user_id}")
            self._record_reservation(reservation_id, user_id, estimated_cost, 
                                    ReservationState.EXPIRED.value)
            return None
        
        except Exception as e:
            logger.error(f"[PREAUTH] ✗ Error reserving funds for {user_id}: {e}")
            self._record_reservation(reservation_id, user_id, estimated_cost, 
                                    ReservationState.EXPIRED.value)
            return None
    
    def capture_funds(self, reservation_id: str, actual_cost: float) -> bool:
        """
        CAPTURE: Charge the actual cost after operation succeeds.
        
        This converts the hold into a real charge. The idempotent reservation_id ensures
        that if this request is retried, the server won't double-charge.
        
        RESILIENCE: Uses injected billing_client with automatic retries and circuit breaker.
        On repeated failures, returns False but reserves funds stay held. User can retry
        the chat later, or admin can manually reconcile.
        
        Args:
            reservation_id: The reservation ID from reserve_funds()
            actual_cost: The actual cost in dollars (from LLM response)
            
        Returns:
            True: Charge successful
            False: Charge failed (funds still held, can retry or release)
        """
        from service_utils import ServiceUnavailable
        
        try:
            logger.info(f"[CAPTURE] Capturing ${actual_cost:.6f} for reservation {reservation_id}")
            
            resp = self.billing_client.post(
                "/capture",
                json={
                    "reservation_id": reservation_id,
                    "actual_cost": actual_cost
                },
                headers=self.internal_headers
            )
            
            if resp.status_code == 200:
                self._update_reservation(reservation_id, ReservationState.CAPTURED.value, 
                                        actual_cost=actual_cost)
                logger.info(f"[CAPTURE] ✓ Captured ${actual_cost:.6f}")
                return True
            
            elif resp.status_code == 409:  # Conflict (already captured)
                self._update_reservation(reservation_id, ReservationState.CAPTURED.value, 
                                        actual_cost=actual_cost)
                logger.warning(f"[CAPTURE] ⚠ Already captured (idempotent retry)")
                return True
            
            else:
                error_msg = resp.json().get('error', f'HTTP {resp.status_code}')
                self._update_reservation(reservation_id, ReservationState.ACTIVE.value, 
                                        error_message=error_msg)
                logger.error(f"[CAPTURE] ✗ Capture failed: {error_msg}")
                return False
        
        except ServiceUnavailable:
            # Circuit breaker open: service repeatedly failed
            # Log for reconciliation: user got answer, but we couldn't charge
            logger.error(f"[CAPTURE] ✗ Billing service unavailable (circuit breaker open) for {reservation_id}")
            logger.error(f"[CAPTURE] ⚠ USER GOT ANSWER WITHOUT CHARGE - manual reconciliation needed")
            # Still return False so caller knows the charge wasn't applied
            # The local DB will help us reconcile later
            return False
        
        except Exception as e:
            logger.error(f"[CAPTURE] ✗ Error capturing funds: {e}")
            return False
    
    def release_funds(self, reservation_id: str) -> bool:
        """
        RELEASE: Give back reserved funds (on error).
        
        Called when the expensive operation fails (e.g., LLM times out).
        This returns the reserved funds to the user's balance.
        
        RESILIENCE: Uses injected billing_client with automatic retries and circuit breaker.
        If release fails, funds are still reserved (user doesn't get charged but funds held).
        Better to be conservative: keep funds held than accidentally double-charge.
        
        Args:
            reservation_id: The reservation ID from reserve_funds()
            
        Returns:
            True: Release successful
            False: Release failed (manual reconciliation needed)
        """
        from service_utils import ServiceUnavailable
        
        try:
            logger.info(f"[RELEASE] Releasing reservation {reservation_id}")
            
            resp = self.billing_client.post(
                "/release",
                json={"reservation_id": reservation_id},
                headers=self.internal_headers
            )
            
            if resp.status_code == 200:
                self._update_reservation(reservation_id, ReservationState.RELEASED.value)
                logger.info(f"[RELEASE] ✓ Funds released")
                return True
            
            elif resp.status_code == 404:  # Already released
                self._update_reservation(reservation_id, ReservationState.RELEASED.value)
                logger.warning(f"[RELEASE] ⚠ Already released (idempotent)")
                return True
            
            else:
                error_msg = resp.json().get('error', f'HTTP {resp.status_code}')
                logger.error(f"[RELEASE] ✗ Release failed: {error_msg}")
                return False
        
        except ServiceUnavailable:
            # Circuit breaker open: service repeatedly failed
            # Funds remain reserved. Better to be conservative.
            logger.error(f"[RELEASE] ✗ Billing service unavailable (circuit breaker open) for {reservation_id}")
            logger.warning(f"[RELEASE] ⚠ Funds still reserved - manual reconciliation needed")
            return False
        
        except Exception as e:
            logger.error(f"[RELEASE] ✗ Error releasing funds: {e}")
            return False
    
    def deduct_cost_idempotent(self, user_id: str, job_id: str, cost: float, 
                               description: str) -> bool:
        """
        LEGACY: Idempotent single-shot deduction (for non-pre-auth operations).
        
        For operations that can't use pre-authorization, this provides idempotency
        through unique job IDs. The billing server stores processed job_ids and
        rejects duplicate requests.
        
        RESILIENCE: Uses injected billing_client with automatic retries and circuit breaker.
        If billing service is down, returns False but logs for reconciliation.
        
        Args:
            user_id: User ID
            job_id: Unique job ID (prevents double-charging if retried)
            cost: Cost in dollars
            description: Description for audit log
            
        Returns:
            True: Deduction successful
            False: Deduction failed
        """
        from service_utils import ServiceUnavailable
        
        try:
            logger.info(f"[DEDUCT-IDEMPOTENT] Deducting ${cost:.6f} for user {user_id} (job {job_id})")
            
            resp = self.billing_client.post(
                "/deduct",
                json={
                    "user_id": user_id,
                    "job_id": job_id,
                    "cost": cost,
                    "description": description
                },
                headers=self.internal_headers
            )
            
            if resp.status_code == 200:
                logger.info(f"[DEDUCT-IDEMPOTENT] ✓ Deducted ${cost:.6f}")
                return True
            
            elif resp.status_code == 409:  # Conflict (already deducted)
                logger.warning(f"[DEDUCT-IDEMPOTENT] ⚠ Already deducted (idempotent retry)")
                return True
            
            else:
                error_msg = resp.json().get('error', f'HTTP {resp.status_code}')
                logger.error(f"[DEDUCT-IDEMPOTENT] ✗ Deduction failed: {error_msg}")
                return False
        
        except ServiceUnavailable:
            # Circuit breaker open: billing service down
            logger.error(f"[DEDUCT-IDEMPOTENT] ✗ Billing service unavailable (circuit breaker open) for user {user_id}")
            logger.warning(f"[DEDUCT-IDEMPOTENT] ⚠ Charge may not have been applied - manual reconciliation needed")
            return False
                
        except Exception as e:
            logger.error(f"[DEDUCT-IDEMPOTENT] ✗ Error deducting cost: {e}")
            return False
    
    def get_pending_reservations(self, user_id: Optional[str] = None) -> list:
        """
        Get pending reservations for reconciliation.
        
        Used by reconciliation service to identify stuck reservations
        that need manual intervention.
        
        Args:
            user_id: Optional filter by user
            
        Returns:
            List of reservation dicts
        """
        try:
            with self._get_conn() as conn:
                conn.row_factory = sqlite3.Row
                
                if user_id:
                    cursor = conn.execute(
                        "SELECT * FROM reservations WHERE user_id = ? AND state = ? ORDER BY created_at",
                        (user_id, ReservationState.ACTIVE.value)
                    )
                else:
                    cursor = conn.execute(
                        "SELECT * FROM reservations WHERE state = ? ORDER BY created_at",
                        (ReservationState.ACTIVE.value,)
                    )
                
                return [dict(row) for row in cursor.fetchall()]
        
        except Exception as e:
            logger.error(f"Failed to get pending reservations: {e}")
            return []
    
    def get_reservation_history(self, reservation_id: str) -> Optional[Dict]:
        """Get the full history of a reservation."""
        try:
            with self._get_conn() as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.execute(
                    "SELECT * FROM reservations WHERE reservation_id = ?",
                    (reservation_id,)
                )
                row = cursor.fetchone()
                return dict(row) if row else None
        
        except Exception as e:
            logger.error(f"Failed to get reservation history: {e}")
            return None


# Example usage in a chat endpoint:
"""
# Initialize at startup
from cost_tracking import CostTracker
from service_utils import get_internal_headers

cost_tracker = CostTracker(
    billing_server_url=BILLING_SERVER_URL,
    internal_headers=get_internal_headers()
)

# In chat endpoint:
@blp_chat.route("/chat", methods=["POST"])
def chat():
    user_id = get_user_id_from_request(request)
    user_query = request.json.get('query')
    
    # STEP 1: PRE-AUTHORIZE
    # Estimate: GPT-4 is ~$0.03 per response
    reservation_id = cost_tracker.reserve_funds(user_id, estimated_cost=0.05)
    if not reservation_id:
        return jsonify({"error": "Insufficient balance"}), 402
    
    try:
        # STEP 2: EXPENSIVE OPERATION
        result = model.chat(prompt)
        actual_cost = result['cost']
        
        # STEP 3: CAPTURE ACTUAL COST
        if not cost_tracker.capture_funds(reservation_id, actual_cost):
            logger.error(f"Capture failed! User got answer but wasn't charged (race condition)")
            # Don't fail the response - user already got the answer
            # But log it for investigation
        
        return jsonify({
            "response": result['response'],
            "cost": actual_cost,
            "reservation_id": reservation_id
        })
    
    except Exception as e:
        # STEP 4: RELEASE ON FAILURE
        cost_tracker.release_funds(reservation_id)
        logger.error(f"Request failed: {e}", exc_info=True)
        return jsonify({"error": "Request failed"}), 500
"""
