import os
from fastapi import FastAPI, Depends, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from backend.database import init_db, get_db
from backend.routers import auth, jobs, applications, contracts, wallet, profile, services, database
from backend.auth_utils import get_current_user_id

app = FastAPI(
    title="Campus Freelance Marketplace",
    description="Smart Campus Digital Freelance Marketplace Management System",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def startup():
    init_db()
    # Ensure uploads dir exists
    uploads_dir = os.path.join(os.path.dirname(__file__), "..", "uploads")
    os.makedirs(uploads_dir, exist_ok=True)


def assert_admin_main(user_id: int):
    db = get_db()
    try:
        user = db.execute("SELECT is_admin FROM users WHERE user_id = ?", (user_id,)).fetchone()
        if not user or user["is_admin"] != 1:
            raise HTTPException(status_code=403, detail="Admin access required.")
    finally:
        db.close()


@app.get("/admin/db-stats")
def get_database_stats(user_id: int = Depends(get_current_user_id)):
    """Debug endpoint to view database statistics and contents."""
    assert_admin_main(user_id)
    db = get_db()
    try:
        stats = {}
        
        # Table counts
        tables = ["users", "categories", "services", "job_requests", "applications", 
                 "contracts", "payments", "ratings", "freelancer_stats", "work_submissions", "wallet_transactions"]
        
        for table in tables:
            count = db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            stats[table] = count
        
        # Recent users
        users = db.execute("""
            SELECT user_id, name, email, wallet_balance, join_date 
            FROM users ORDER BY join_date DESC LIMIT 5
        """).fetchall()
        stats["recent_users"] = [dict(u) for u in users]
        
        # Recent jobs
        jobs = db.execute("""
            SELECT j.job_id, j.title, j.status, j.budget, u.name as client_name
            FROM job_requests j
            JOIN users u ON j.client_id = u.user_id
            ORDER BY j.created_date DESC LIMIT 5
        """).fetchall()
        stats["recent_jobs"] = [dict(j) for j in jobs]
        
        # Wallet summary
        wallet_summary = db.execute("""
            SELECT 
                COUNT(*) as total_users,
                SUM(wallet_balance) as total_balance,
                AVG(wallet_balance) as avg_balance,
                MIN(wallet_balance) as min_balance,
                MAX(wallet_balance) as max_balance
            FROM users
        """).fetchone()
        stats["wallet_summary"] = dict(wallet_summary)
        
        # Contract summary
        contract_summary = db.execute("""
            SELECT 
                COUNT(*) as total_contracts,
                SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) as completed_contracts,
                SUM(CASE WHEN status = 'active' THEN 1 ELSE 0 END) as active_contracts,
                SUM(CASE WHEN status = 'submitted' THEN 1 ELSE 0 END) as submitted_contracts,
                AVG(agreed_price) as avg_contract_value
            FROM contracts
        """).fetchone()
        stats["contract_summary"] = dict(contract_summary)
        
        return stats
    finally:
        db.close()


@app.get("/admin/db-tables/{table_name}")
def get_table_data(table_name: str, limit: int = 10, user_id: int = Depends(get_current_user_id)):
    """Debug endpoint to view specific table data."""
    assert_admin_main(user_id)
    allowed_tables = ["users", "categories", "services", "job_requests", "applications", 
                     "contracts", "payments", "ratings", "freelancer_stats", "work_submissions", "wallet_transactions"]
    
    if table_name not in allowed_tables:
        return {"error": f"Table '{table_name}' not allowed. Allowed: {allowed_tables}"}
    
    db = get_db()
    try:
        # Get column names
        columns = db.execute(f"PRAGMA table_info({table_name})").fetchall()
        column_names = [col[1] for col in columns]
        
        # Get data
        rows = db.execute(f"SELECT * FROM {table_name} LIMIT ?", (limit,)).fetchall()
        data = [dict(zip(column_names, row)) for row in rows]
        
        return {
            "table": table_name,
            "columns": column_names,
            "row_count": len(data),
            "data": data
        }
    finally:
        db.close()


app.include_router(auth.router, prefix="/auth", tags=["auth"])
app.include_router(jobs.router, prefix="/jobs", tags=["jobs"])
app.include_router(applications.router, prefix="/applications", tags=["applications"])
app.include_router(contracts.router, prefix="/contracts", tags=["contracts"])
app.include_router(wallet.router, prefix="/wallet", tags=["wallet"])
app.include_router(profile.router, prefix="/profile", tags=["profile"])
app.include_router(services.router, prefix="/services", tags=["services"])
app.include_router(database.router, prefix="/database", tags=["database"])

# Serve frontend static files — must be last
FRONTEND_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "frontend")
app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
