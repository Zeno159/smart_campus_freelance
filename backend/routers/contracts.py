import os
import uuid
from fastapi import APIRouter, HTTPException, Depends, UploadFile, File, Form
from starlette.responses import FileResponse
from pydantic import BaseModel
from backend.database import get_db
from backend.auth_utils import get_current_user_id

router = APIRouter()

UPLOAD_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "uploads")
ALLOWED_EXTENSIONS = {"pdf", "jpeg", "jpg", "png", "docx"}
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB

MIME_MAP = {
    "application/pdf": "pdf",
    "image/jpeg": "jpeg",
    "image/jpg": "jpg",
    "image/png": "png",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "docx",
}

os.makedirs(UPLOAD_DIR, exist_ok=True)


@router.post("/{contract_id}/submit")
async def submit_work(
    contract_id: int,
    notes: str = Form(""),
    file: UploadFile = File(...),
    user_id: int = Depends(get_current_user_id),
):
    db = get_db()
    try:
        contract = db.execute("SELECT * FROM contracts WHERE contract_id = ?", (contract_id,)).fetchone()
        if not contract:
            raise HTTPException(404, "Contract not found.")
        if contract["freelancer_id"] != user_id:
            raise HTTPException(403, "Only the assigned freelancer can submit work.")
        if contract["status"] not in ("active",):
            raise HTTPException(400, "Work has already been submitted for this contract.")

        # Validate file
        if not file or not file.filename:
            raise HTTPException(400, "Please attach your work before submitting.")

        ext = file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else ""
        if ext not in ALLOWED_EXTENSIONS:
            raise HTTPException(400, "Only PDF, JPEG, PNG, and DOCX files are allowed.")

        content = await file.read()
        if len(content) > MAX_FILE_SIZE:
            raise HTTPException(400, "File size must be under 10MB.")

        # Validate MIME type
        content_type = file.content_type or ""
        file_type = MIME_MAP.get(content_type, ext)
        if file_type not in ALLOWED_EXTENSIONS:
            raise HTTPException(400, "Invalid file type detected.")

        # Save file with UUID name
        safe_name = f"{uuid.uuid4()}.{ext}"
        file_path = os.path.join(UPLOAD_DIR, safe_name)
        with open(file_path, "wb") as f:
            f.write(content)

        # Insert submission
        db.execute(
            "INSERT INTO work_submissions (contract_id, file_path, file_type, notes) VALUES (?,?,?,?)",
            (contract_id, file_path, file_type, notes.strip()),
        )
        # Update contract status
        db.execute(
            "UPDATE contracts SET status = 'submitted' WHERE contract_id = ?", (contract_id,)
        )
        # Update job status
        db.execute(
            "UPDATE job_requests SET status = 'submitted' WHERE job_id = ?", (contract["job_id"],)
        )
        db.commit()
        return {"message": "Work submitted successfully. Awaiting client review."}
    finally:
        db.close()


@router.get("/{contract_id}/submission/download")
def download_submission(contract_id: int, user_id: int = Depends(get_current_user_id)):
    """Download submitted work file. Accessible to client and freelancer."""
    db = get_db()
    try:
        contract = db.execute("SELECT * FROM contracts WHERE contract_id = ?", (contract_id,)).fetchone()
        if not contract:
            raise HTTPException(404, "Contract not found.")
        
        # Verify user is either the client or the freelancer
        job = db.execute("SELECT client_id FROM job_requests WHERE job_id = ?", (contract["job_id"],)).fetchone()
        is_client = job["client_id"] == user_id
        is_freelancer = contract["freelancer_id"] == user_id
        
        if not (is_client or is_freelancer):
            raise HTTPException(403, "You don't have permission to download this file.")
        
        sub = db.execute(
            "SELECT * FROM work_submissions WHERE contract_id = ?", (contract_id,)
        ).fetchone()
        if not sub:
            raise HTTPException(404, "No work submission found for this contract.")
        
        file_path = sub["file_path"]
        if not os.path.exists(file_path):
            raise HTTPException(404, "File not found on server.")
        
        filename = f"work_{contract_id}.{sub['file_type']}"
        return FileResponse(file_path, filename=filename)
    finally:
        db.close()


class CompleteRequest(BaseModel):
    rating_score: float
    review_text: str = ""


@router.post("/{contract_id}/complete")
def complete_job(
    contract_id: int,
    req: CompleteRequest,
    user_id: int = Depends(get_current_user_id),
):
    if not (1 <= req.rating_score <= 5):
        raise HTTPException(400, "Rating must be between 1 and 5.")

    db = get_db()
    try:
        contract = db.execute("SELECT * FROM contracts WHERE contract_id = ?", (contract_id,)).fetchone()
        if not contract:
            raise HTTPException(404, "Contract not found.")

        # Verify caller is the client of the job
        job = db.execute("SELECT * FROM job_requests WHERE job_id = ?", (contract["job_id"],)).fetchone()
        if job["client_id"] != user_id:
            raise HTTPException(403, "Only the client can mark a job as complete.")
        if contract["status"] != "submitted":
            raise HTTPException(400, "Work must be submitted before the job can be completed.")

        # Check no rating exists
        existing_rating = db.execute(
            "SELECT rating_id FROM ratings WHERE contract_id = ?", (contract_id,)
        ).fetchone()
        if existing_rating:
            raise HTTPException(400, "This contract has already been rated.")

        # Insert rating
        db.execute(
            "INSERT INTO ratings (contract_id, rating_score, review_text) VALUES (?,?,?)",
            (contract_id, req.rating_score, req.review_text.strip()),
        )

        # Get payment record
        payment = db.execute(
            "SELECT * FROM payments WHERE contract_id = ?", (contract_id,)
        ).fetchone()

        # Release payment to freelancer
        db.execute(
            "UPDATE payments SET payment_status = 'released', payment_date = datetime('now') WHERE contract_id = ?",
            (contract_id,),
        )
        
        # Credit freelancer
        db.execute(
            "UPDATE users SET wallet_balance = wallet_balance + ? WHERE user_id = ?",
            (payment["freelancer_amount"], contract["freelancer_id"]),
        )
        db.execute(
            "INSERT INTO wallet_transactions (user_id, amount, txn_type, description) VALUES (?,?,'credit',?)",
            (contract["freelancer_id"], payment["freelancer_amount"],
             f"Payment for contract #{contract_id} (after 1% commission)"),
        )
        
        # Debit client (release the hold and convert to actual debit)
        db.execute(
            "UPDATE users SET wallet_balance = wallet_balance - ? WHERE user_id = ?",
            (payment["total_amount"], job["client_id"]),
        )
        db.execute(
            "INSERT INTO wallet_transactions (user_id, amount, txn_type, description) VALUES (?,?,'debit',?)",
            (job["client_id"], payment["total_amount"],
             f"Payment released for contract #{contract_id}"),
        )

        # Update contract and job status
        db.execute(
            "UPDATE contracts SET status = 'completed', completion_date = datetime('now') WHERE contract_id = ?",
            (contract_id,),
        )
        db.execute(
            "UPDATE job_requests SET status = 'completed' WHERE job_id = ?", (contract["job_id"],)
        )

        # Update freelancer stats
        stats = db.execute(
            "SELECT * FROM freelancer_stats WHERE freelancer_id = ?", (contract["freelancer_id"],)
        ).fetchone()
        if stats:
            all_ratings = db.execute(
                """SELECT AVG(r.rating_score) AS avg_r, COUNT(r.rating_id) AS cnt
                   FROM ratings r
                   JOIN contracts c ON r.contract_id = c.contract_id
                   WHERE c.freelancer_id = ?""",
                (contract["freelancer_id"],),
            ).fetchone()
            total_earnings = db.execute(
                """SELECT COALESCE(SUM(p.freelancer_amount), 0) AS total
                   FROM payments p
                   JOIN contracts c ON p.contract_id = c.contract_id
                   WHERE c.freelancer_id = ? AND p.payment_status = 'released'""",
                (contract["freelancer_id"],),
            ).fetchone()
            db.execute(
                """UPDATE freelancer_stats SET avg_rating = ?, total_jobs = ?, total_earnings = ?
                   WHERE freelancer_id = ?""",
                (
                    round(all_ratings["avg_r"] or 0, 2),
                    all_ratings["cnt"],
                    total_earnings["total"],
                    contract["freelancer_id"],
                ),
            )
        else:
            db.execute(
                "INSERT INTO freelancer_stats (freelancer_id, avg_rating, total_jobs, total_earnings) VALUES (?,?,1,?)",
                (contract["freelancer_id"], req.rating_score, payment["freelancer_amount"]),
            )

        db.commit()
        return {"message": "Job completed. Payment released to freelancer."}
    finally:
        db.close()
