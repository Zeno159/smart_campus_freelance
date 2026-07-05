from fastapi import APIRouter, HTTPException, Depends
from backend.database import get_db
from backend.auth_utils import get_current_user_id

router = APIRouter()


@router.get("")
def get_profile(user_id: int = Depends(get_current_user_id)):
    db = get_db()
    try:
        user = db.execute(
            "SELECT user_id, name, email, contact, wallet_balance, join_date FROM users WHERE user_id = ?",
            (user_id,),
        ).fetchone()
        if not user:
            raise HTTPException(404, "User not found.")

        stats = db.execute(
            "SELECT * FROM freelancer_stats WHERE freelancer_id = ?", (user_id,)
        ).fetchone()

        # Posted jobs (as client)
        posted_jobs = db.execute(
            """SELECT jr.*, c.category_name,
                      (SELECT COUNT(*) FROM applications a WHERE a.job_id = jr.job_id) AS app_count
               FROM job_requests jr
               LEFT JOIN categories c ON jr.category_id = c.category_id
               WHERE jr.client_id = ?
               ORDER BY jr.created_date DESC""",
            (user_id,),
        ).fetchall()

        # Applications made (as freelancer)
        applications = db.execute(
            """SELECT a.*, jr.title AS job_title, jr.budget, jr.status AS job_status,
                      u.name AS client_name
               FROM applications a
               JOIN job_requests jr ON a.job_id = jr.job_id
               JOIN users u ON jr.client_id = u.user_id
               WHERE a.freelancer_id = ?
               ORDER BY a.applied_date DESC""",
            (user_id,),
        ).fetchall()

        # Active/ongoing contracts (as freelancer)
        active_contracts = db.execute(
            """SELECT ct.*, jr.title AS job_title, u.name AS client_name
               FROM contracts ct
               JOIN job_requests jr ON ct.job_id = jr.job_id
               JOIN users u ON jr.client_id = u.user_id
               WHERE ct.freelancer_id = ? AND ct.status IN ('active','submitted')
               ORDER BY ct.start_date DESC""",
            (user_id,),
        ).fetchall()

        # Completed work (as freelancer)
        completed_work = db.execute(
            """SELECT ct.*, jr.title AS job_title, u.name AS client_name,
                      r.rating_score, r.review_text, p.freelancer_amount AS earned
               FROM contracts ct
               JOIN job_requests jr ON ct.job_id = jr.job_id
               JOIN users u ON jr.client_id = u.user_id
               LEFT JOIN ratings r ON r.contract_id = ct.contract_id
               LEFT JOIN payments p ON p.contract_id = ct.contract_id
               WHERE ct.freelancer_id = ? AND ct.status = 'completed'
               ORDER BY ct.completion_date DESC""",
            (user_id,),
        ).fetchall()

        # Services
        services = db.execute(
            """SELECT s.*, c.category_name FROM services s
               LEFT JOIN categories c ON s.category_id = c.category_id
               WHERE s.user_id = ? ORDER BY s.created_date DESC""",
            (user_id,),
        ).fetchall()

        # Wallet transactions
        transactions = db.execute(
            "SELECT * FROM wallet_transactions WHERE user_id = ? ORDER BY txn_date DESC LIMIT 20",
            (user_id,),
        ).fetchall()

        return {
            "user": dict(user),
            "stats": dict(stats) if stats else {"avg_rating": 0, "total_jobs": 0, "total_earnings": 0},
            "posted_jobs": [dict(r) for r in posted_jobs],
            "applications": [dict(r) for r in applications],
            "active_contracts": [dict(r) for r in active_contracts],
            "completed_work": [dict(r) for r in completed_work],
            "services": [dict(r) for r in services],
            "transactions": [dict(r) for r in transactions],
        }
    finally:
        db.close()
