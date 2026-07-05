from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from backend.database import get_db
from backend.auth_utils import get_current_user_id

router = APIRouter()


class ApplyRequest(BaseModel):
    job_id: int
    proposed_price: float


@router.post("")
def apply_to_job(req: ApplyRequest, user_id: int = Depends(get_current_user_id)):
    if req.proposed_price <= 0:
        raise HTTPException(400, "Proposed price must be greater than zero.")

    db = get_db()
    try:
        job = db.execute("SELECT * FROM job_requests WHERE job_id = ?", (req.job_id,)).fetchone()
        if not job:
            raise HTTPException(404, "Job not found.")
        if job["status"] != "open":
            raise HTTPException(400, "This job is no longer accepting applications.")
        if job["client_id"] == user_id:
            raise HTTPException(400, "You cannot apply to your own job.")

        # Check duplicate application
        existing = db.execute(
            "SELECT application_id FROM applications WHERE job_id = ? AND freelancer_id = ?",
            (req.job_id, user_id),
        ).fetchone()
        if existing:
            raise HTTPException(400, "You have already applied to this job.")

        # Check if user already has an active contract (one job at a time)
        active = db.execute(
            "SELECT contract_id FROM contracts WHERE freelancer_id = ? AND status IN ('active','submitted')",
            (user_id,),
        ).fetchone()
        if active:
            raise HTTPException(400, "You are currently working on another job. Complete it first.")

        # Check client wallet vs proposed price
        client = db.execute(
            "SELECT wallet_balance FROM users WHERE user_id = ?", (job["client_id"],)
        ).fetchone()
        if client["wallet_balance"] < req.proposed_price:
            raise HTTPException(
                400, "Insufficient funds. The client cannot afford your proposed price."
            )

        cursor = db.execute(
            "INSERT INTO applications (job_id, freelancer_id, proposed_price) VALUES (?, ?, ?)",
            (req.job_id, user_id, req.proposed_price),
        )
        db.commit()
        return {"application_id": cursor.lastrowid, "message": "Application submitted successfully."}
    finally:
        db.close()


@router.put("/{application_id}/accept")
def accept_application(application_id: int, user_id: int = Depends(get_current_user_id)):
    db = get_db()
    try:
        app = db.execute(
            "SELECT * FROM applications WHERE application_id = ?", (application_id,)
        ).fetchone()
        if not app:
            raise HTTPException(404, "Application not found.")

        job = db.execute("SELECT * FROM job_requests WHERE job_id = ?", (app["job_id"],)).fetchone()
        if job["client_id"] != user_id:
            raise HTTPException(403, "Only the job poster can accept applications.")
        if job["status"] != "open":
            raise HTTPException(400, "This job is no longer open.")
        if app["status"] != "pending":
            raise HTTPException(400, "This application has already been processed.")

        agreed_price = app["proposed_price"]

        # Check if client has enough wallet balance
        client = db.execute("SELECT wallet_balance FROM users WHERE user_id = ?", (user_id,)).fetchone()
        if client["wallet_balance"] < agreed_price:
            raise HTTPException(
                400,
                f"Insufficient wallet balance. You need Rs.{agreed_price:.2f} but have Rs.{client['wallet_balance']:.2f}.",
            )

        # Debit client wallet (hold)
        db.execute(
            "UPDATE users SET wallet_balance = wallet_balance - ? WHERE user_id = ?",
            (agreed_price, user_id),
        )
        db.execute(
            "INSERT INTO wallet_transactions (user_id, amount, txn_type, description) VALUES (?, ?, 'hold', ?)",
            (user_id, agreed_price, f"Wallet hold for job: {job['title']}"),
        )

        # Accept this application
        db.execute(
            "UPDATE applications SET status = 'accepted' WHERE application_id = ?",
            (application_id,),
        )

        # Reject all other pending applications for this job
        db.execute(
            "UPDATE applications SET status = 'rejected' WHERE job_id = ? AND application_id != ?",
            (app["job_id"], application_id),
        )

        # Update job status
        db.execute(
            "UPDATE job_requests SET status = 'assigned' WHERE job_id = ?", (app["job_id"],)
        )

        # Create contract
        cursor = db.execute(
            "INSERT INTO contracts (job_id, freelancer_id, agreed_price) VALUES (?, ?, ?)",
            (app["job_id"], app["freelancer_id"], agreed_price),
        )
        contract_id = cursor.lastrowid

        # Create pending payment record
        commission = round(agreed_price * 0.01, 2)
        freelancer_amount = round(agreed_price - commission, 2)
        db.execute(
            "INSERT INTO payments (contract_id, total_amount, commission_amount, freelancer_amount) VALUES (?,?,?,?)",
            (contract_id, agreed_price, commission, freelancer_amount),
        )

        db.commit()
        return {"contract_id": contract_id, "message": "Application accepted. Contract created."}
    finally:
        db.close()


@router.put("/{application_id}/reject")
def reject_application(application_id: int, user_id: int = Depends(get_current_user_id)):
    db = get_db()
    try:
        app = db.execute(
            "SELECT * FROM applications WHERE application_id = ?", (application_id,)
        ).fetchone()
        if not app:
            raise HTTPException(404, "Application not found.")

        job = db.execute("SELECT * FROM job_requests WHERE job_id = ?", (app["job_id"],)).fetchone()
        if job["client_id"] != user_id:
            raise HTTPException(403, "Only the job poster can reject applications.")
        if app["status"] != "pending":
            raise HTTPException(400, "This application has already been processed.")

        db.execute(
            "UPDATE applications SET status = 'rejected' WHERE application_id = ?",
            (application_id,),
        )
        db.commit()
        return {"message": "Application rejected."}
    finally:
        db.close()
