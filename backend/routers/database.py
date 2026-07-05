from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from backend.database import get_db
from backend.auth_utils import get_current_user_id

router = APIRouter()


def assert_admin(user_id: int):
    db = get_db()
    try:
        user = db.execute("SELECT is_admin FROM users WHERE user_id = ?", (user_id,)).fetchone()
        if not user or user["is_admin"] != 1:
            raise HTTPException(status_code=403, detail="Admin access required.")
    finally:
        db.close()

@router.get("/stats")
def get_database_stats(user_id: int = Depends(get_current_user_id)):
    """Get overall database statistics"""
    assert_admin(user_id)
    db = get_db()
    try:
        stats = {}

        # Basic table counts
        tables = ['users', 'job_requests', 'applications', 'contracts', 'payments',
                 'ratings', 'work_submissions', 'wallet_transactions', 'services']

        for table in tables:
            count = db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            stats[table] = count

        # Enhanced admin stats
        # Total earnings from commissions
        commission_earnings = db.execute("""
            SELECT COALESCE(SUM(commission_amount), 0) as total_commission
            FROM payments
            WHERE payment_status = 'released'
        """).fetchone()[0]
        stats['total_commission_earnings'] = float(commission_earnings)

        # Total platform revenue (all payments)
        total_revenue = db.execute("""
            SELECT COALESCE(SUM(total_amount), 0) as total_revenue
            FROM payments
            WHERE payment_status = 'released'
        """).fetchone()[0]
        stats['total_platform_revenue'] = float(total_revenue)

        # Active contracts
        active_contracts = db.execute("""
            SELECT COUNT(*) FROM contracts
            WHERE status IN ('active', 'submitted')
        """).fetchone()[0]
        stats['active_contracts'] = active_contracts

        # Completed contracts
        completed_contracts = db.execute("""
            SELECT COUNT(*) FROM contracts
            WHERE status = 'completed'
        """).fetchone()[0]
        stats['completed_contracts'] = completed_contracts

        # Total wallet balance across all users
        total_wallet_balance = db.execute("""
            SELECT COALESCE(SUM(wallet_balance), 0) as total_balance
            FROM users
        """).fetchone()[0]
        stats['total_wallet_balance'] = float(total_wallet_balance)

        # Recent activity (last 7 days)
        recent_jobs = db.execute("""
            SELECT COUNT(*) FROM job_requests
            WHERE created_date >= datetime('now', '-7 days')
        """).fetchone()[0]
        stats['recent_jobs_7d'] = recent_jobs

        recent_contracts = db.execute("""
            SELECT COUNT(*) FROM contracts
            WHERE start_date >= datetime('now', '-7 days')
        """).fetchone()[0]
        stats['recent_contracts_7d'] = recent_contracts

        return stats
    finally:
        db.close()

@router.get("/table/{table_name}")
def get_table_data(
    table_name: str,
    search: Optional[str] = None,
    limit: int = 50,
    page: int = 1,
    user_id: int = Depends(get_current_user_id),
):
    """Get data from a specific table with pagination and optional search"""
    assert_admin(user_id)
    allowed_tables = ['users', 'job_requests', 'applications', 'contracts', 'payments',
                     'ratings', 'work_submissions', 'wallet_transactions', 'services',
                     'categories', 'freelancer_stats']

    if table_name not in allowed_tables:
        raise HTTPException(status_code=400, detail="Table not accessible")

    if limit <= 0:
        limit = 50
    if limit > 100:
        limit = 100
    if page <= 0:
        page = 1

    offset = (page - 1) * limit
    search = search.strip() if search else ""

    db = get_db()
    try:
        columns = db.execute(f"PRAGMA table_info({table_name})").fetchall()
        column_names = [col[1] for col in columns]

        query = f"SELECT * FROM {table_name}"
        count_query = f"SELECT COUNT(*) FROM {table_name}"
        params = []
        where_clauses = []

        if search:
            if table_name == 'users':
                where_clauses.append("(name LIKE ? OR email LIKE ? OR contact LIKE ?)")
                params.extend([f"%{search}%", f"%{search}%", f"%{search}%"])
            elif table_name == 'wallet_transactions':
                if search.isdigit():
                    where_clauses.append("(txn_id = ? OR user_id = ? OR description LIKE ?)")
                    params.extend([int(search), int(search), f"%{search}%"])
                else:
                    where_clauses.append("description LIKE ?")
                    params.append(f"%{search}%")
            elif table_name == 'contracts':
                if search.isdigit():
                    where_clauses.append("(contract_id = ? OR job_id = ? OR freelancer_id = ? OR status LIKE ?)")
                    params.extend([int(search), int(search), int(search), f"%{search}%"])
                else:
                    where_clauses.append("status LIKE ?")
                    params.append(f"%{search}%")
            elif table_name == 'categories':
                where_clauses.append("category_name LIKE ?")
                params.append(f"%{search}%")
            elif table_name == 'services':
                if search.isdigit():
                    where_clauses.append("(title LIKE ? OR user_id = ?)")
                    params.extend([f"%{search}%", int(search)])
                else:
                    where_clauses.append("title LIKE ?")
                    params.append(f"%{search}%")
            elif table_name == 'job_requests':
                if search.isdigit():
                    where_clauses.append("(title LIKE ? OR job_id = ? OR client_id = ? OR status LIKE ?)")
                    params.extend([f"%{search}%", int(search), int(search), f"%{search}%"])
                else:
                    where_clauses.append("(title LIKE ? OR status LIKE ?)")
                    params.extend([f"%{search}%", f"%{search}%"])
            elif table_name == 'applications':
                if search.isdigit():
                    where_clauses.append("(application_id = ? OR job_id = ? OR freelancer_id = ? OR status LIKE ?)")
                    params.extend([int(search), int(search), int(search), f"%{search}%"])
                else:
                    where_clauses.append("status LIKE ?")
                    params.append(f"%{search}%")
            elif table_name == 'payments':
                if search.isdigit():
                    where_clauses.append("(payment_id = ? OR contract_id = ? OR payment_status LIKE ?)")
                    params.extend([int(search), int(search), f"%{search}%"])
                else:
                    where_clauses.append("payment_status LIKE ?")
                    params.append(f"%{search}%")
            elif table_name == 'ratings':
                if search.isdigit():
                    where_clauses.append("(rating_id = ? OR contract_id = ?)")
                    params.extend([int(search), int(search)])
                else:
                    where_clauses.append("review_text LIKE ?")
                    params.append(f"%{search}%")
            elif table_name == 'freelancer_stats':
                if search.isdigit():
                    where_clauses.append("freelancer_id = ?")
                    params.append(int(search))
            elif table_name == 'work_submissions':
                if search.isdigit():
                    where_clauses.append("(submission_id = ? OR contract_id = ? OR file_type LIKE ?)")
                    params.extend([int(search), int(search), f"%{search}%"])
                else:
                    where_clauses.append("(file_type LIKE ? OR notes LIKE ?)")
                    params.extend([f"%{search}%", f"%{search}%"])

        if where_clauses:
            where_sql = " WHERE " + " AND ".join(where_clauses)
            query += where_sql
            count_query += where_sql

        query += " ORDER BY rowid ASC LIMIT ? OFFSET ?"
        rows = db.execute(query, (*params, limit, offset)).fetchall()
        total_count = db.execute(count_query, params).fetchone()[0]
        data = [dict(zip(column_names, row)) for row in rows]

        return {
            "columns": column_names,
            "data": data,
            "count": len(data),
            "total_count": total_count,
            "limit": limit,
            "page": page,
        }
    finally:
        db.close()

@router.get("/users/summary")
def get_users_summary(user_id: int = Depends(get_current_user_id)):
    """Get user summary with balances and stats"""
    assert_admin(user_id)
    db = get_db()
    try:
        users = db.execute("""
            SELECT u.user_id, u.name, u.email, u.contact, u.wallet_balance,
                   COALESCE(fs.avg_rating, 0) as avg_rating,
                   COALESCE(fs.total_jobs, 0) as total_jobs,
                   COALESCE(fs.total_earnings, 0) as total_earnings
            FROM users u
            LEFT JOIN freelancer_stats fs ON u.user_id = fs.freelancer_id
            ORDER BY u.user_id
        """).fetchall()

        return [dict(user) for user in users]
    finally:
        db.close()

@router.get("/jobs/summary")
def get_jobs_summary(user_id: int = Depends(get_current_user_id)):
    """Get jobs summary with relationships"""
    assert_admin(user_id)
    db = get_db()
    try:
        jobs = db.execute("""
            SELECT j.job_id, j.title, j.status, j.budget, j.expected_date,
                   j.created_date, c.category_name,
                   u.name as client_name,
                   (SELECT COUNT(*) FROM applications a WHERE a.job_id = j.job_id) as applications_count
            FROM job_requests j
            JOIN users u ON j.client_id = u.user_id
            LEFT JOIN categories c ON j.category_id = c.category_id
            ORDER BY j.created_date DESC
        """).fetchall()

        return [dict(job) for job in jobs]
    finally:
        db.close()

@router.get("/contracts/summary")
def get_contracts_summary(user_id: int = Depends(get_current_user_id)):
    """Get contracts summary with relationships"""
    assert_admin(user_id)
    db = get_db()
    try:
        contracts = db.execute("""
            SELECT c.contract_id, c.status, c.agreed_price, c.start_date, c.completion_date,
                   j.title as job_title,
                   u1.name as client_name,
                   u2.name as freelancer_name,
                   p.payment_status,
                   COALESCE(r.rating_score, 0) as rating
            FROM contracts c
            JOIN job_requests j ON c.job_id = j.job_id
            JOIN users u1 ON j.client_id = u1.user_id
            JOIN users u2 ON c.freelancer_id = u2.user_id
            LEFT JOIN payments p ON c.contract_id = p.contract_id
            LEFT JOIN ratings r ON c.contract_id = r.contract_id
            ORDER BY c.contract_id
        """).fetchall()

        return [dict(contract) for contract in contracts]
    finally:
        db.close()

@router.get("/wallet/transactions")
def get_wallet_transactions(user_id: int = Depends(get_current_user_id)):
    """Get all wallet transactions"""
    assert_admin(user_id)
    db = get_db()
    try:
        transactions = db.execute("""
            SELECT t.txn_id, t.amount, t.txn_type, t.description, t.txn_date,
                   u.name as user_name, u.email as user_email
            FROM wallet_transactions t
            JOIN users u ON t.user_id = u.user_id
            ORDER BY t.txn_date DESC
        """).fetchall()

        return [dict(txn) for txn in transactions]
    finally:
        db.close()