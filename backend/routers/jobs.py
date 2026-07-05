from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import Optional
from backend.database import get_db
from backend.auth_utils import get_current_user_id

router = APIRouter()


class CreateJobRequest(BaseModel):
    title: str
    category_id: int
    description: str
    budget: float
    expected_date: str  # ISO date string YYYY-MM-DD


@router.get("")
def list_jobs(search: Optional[str] = None, category_id: Optional[int] = None, user_id: int = Depends(get_current_user_id)):
    db = get_db()
    try:
        query = """
            SELECT
                jr.job_id, jr.title, jr.description, jr.budget, jr.expected_date,
                jr.status, jr.created_date, jr.category_id,
                c.category_name,
                u.name AS client_name, u.user_id AS client_id,
                COALESCE(fs.avg_rating, 0) AS client_rating,
                (SELECT COUNT(*) FROM applications a WHERE a.job_id = jr.job_id) AS application_count
            FROM job_requests jr
            JOIN users u ON jr.client_id = u.user_id
            LEFT JOIN categories c ON jr.category_id = c.category_id
            LEFT JOIN freelancer_stats fs ON u.user_id = fs.freelancer_id
            WHERE jr.status = 'open'
        """
        params = []

        if search:
            query += " AND (jr.title LIKE ? OR u.name LIKE ?)"
            params += [f"%{search}%", f"%{search}%"]

        if category_id:
            query += " AND jr.category_id = ?"
            params.append(category_id)

        query += " ORDER BY jr.created_date DESC"
        rows = db.execute(query, params).fetchall()
        return [dict(r) for r in rows]
    finally:
        db.close()


@router.post("")
def create_job(req: CreateJobRequest, user_id: int = Depends(get_current_user_id)):
    from datetime import date
    title = req.title.strip()
    description = req.description.strip()

    if not title or not description or not req.expected_date:
        raise HTTPException(400, "All fields are required.")
    if req.budget <= 0:
        raise HTTPException(400, "Budget must be greater than zero.")

    try:
        exp_date = date.fromisoformat(req.expected_date)
    except ValueError:
        raise HTTPException(400, "Invalid date format. Use YYYY-MM-DD.")

    if exp_date <= date.today():
        raise HTTPException(400, "Expected date must be in the future.")

    db = get_db()
    try:
        user = db.execute("SELECT wallet_balance FROM users WHERE user_id = ?", (user_id,)).fetchone()
        if user["wallet_balance"] < req.budget:
            raise HTTPException(400, "Insufficient wallet balance. Please top up before posting a job.")

        cursor = db.execute(
            """INSERT INTO job_requests (client_id, category_id, title, description, budget, expected_date)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (user_id, req.category_id, title, description, req.budget, req.expected_date),
        )
        db.commit()
        return {"job_id": cursor.lastrowid, "message": "Job posted successfully."}
    finally:
        db.close()


@router.get("/{job_id}")
def get_job(job_id: int, user_id: int = Depends(get_current_user_id)):
    db = get_db()
    try:
        job = db.execute(
            """
            SELECT
                jr.*, c.category_name,
                u.name AS client_name, u.user_id AS client_id,
                COALESCE(fs.avg_rating, 0) AS client_rating
            FROM job_requests jr
            JOIN users u ON jr.client_id = u.user_id
            LEFT JOIN categories c ON jr.category_id = c.category_id
            LEFT JOIN freelancer_stats fs ON u.user_id = fs.freelancer_id
            WHERE jr.job_id = ?
            """,
            (job_id,),
        ).fetchone()
        if not job:
            raise HTTPException(404, "Job not found.")

        job_dict = dict(job)

        # Applications (only visible to the job poster)
        if job_dict["client_id"] == user_id:
            apps = db.execute(
                """
                SELECT a.*, u.name AS freelancer_name, COALESCE(fs.avg_rating, 0) AS freelancer_rating,
                       fs.total_jobs
                FROM applications a
                JOIN users u ON a.freelancer_id = u.user_id
                LEFT JOIN freelancer_stats fs ON a.freelancer_id = fs.freelancer_id
                WHERE a.job_id = ?
                ORDER BY a.applied_date DESC
                """,
                (job_id,),
            ).fetchall()
            job_dict["applications"] = [dict(a) for a in apps]
        else:
            # Show the current user's own application if any
            my_app = db.execute(
                "SELECT * FROM applications WHERE job_id = ? AND freelancer_id = ?",
                (job_id, user_id),
            ).fetchone()
            job_dict["my_application"] = dict(my_app) if my_app else None
            job_dict["applications"] = None

        # Contract info if assigned/submitted/completed
        contract = db.execute(
            """
            SELECT ct.*, u.name AS freelancer_name
            FROM contracts ct
            JOIN users u ON ct.freelancer_id = u.user_id
            WHERE ct.job_id = ?
            """,
            (job_id,),
        ).fetchone()
        job_dict["contract"] = dict(contract) if contract else None

        # Work submission
        if contract:
            sub = db.execute(
                "SELECT * FROM work_submissions WHERE contract_id = ?",
                (contract["contract_id"],),
            ).fetchone()
            job_dict["submission"] = dict(sub) if sub else None
            rating = db.execute(
                "SELECT * FROM ratings WHERE contract_id = ?",
                (contract["contract_id"],),
            ).fetchone()
            job_dict["rating"] = dict(rating) if rating else None
        else:
            job_dict["submission"] = None
            job_dict["rating"] = None

        job_dict["viewer_is_client"] = job_dict["client_id"] == user_id
        job_dict["viewer_user_id"] = user_id
        return job_dict
    finally:
        db.close()


@router.delete("/{job_id}")
def cancel_job(job_id: int, user_id: int = Depends(get_current_user_id)):
    db = get_db()
    try:
        job = db.execute("SELECT * FROM job_requests WHERE job_id = ?", (job_id,)).fetchone()
        if not job:
            raise HTTPException(404, "Job not found.")
        if job["client_id"] != user_id:
            raise HTTPException(403, "You can only cancel your own jobs.")
        if job["status"] != "open":
            raise HTTPException(400, "Only open jobs can be cancelled.")

        # Check if any applications exist
        app_count = db.execute(
            "SELECT COUNT(*) FROM applications WHERE job_id = ?", (job_id,)
        ).fetchone()[0]
        if app_count > 0:
            raise HTTPException(400, "Cannot remove a job that has received applications.")

        db.execute("UPDATE job_requests SET status = 'cancelled' WHERE job_id = ?", (job_id,))
        db.commit()
        return {"message": "Job cancelled successfully."}
    finally:
        db.close()
