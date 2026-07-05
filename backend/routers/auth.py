import re
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from backend.database import get_db
from backend.auth_utils import hash_password, verify_password, create_token, get_current_user_id

router = APIRouter()

EMAIL_RE = re.compile(r"^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$")


class RegisterRequest(BaseModel):
    name: str
    email: str
    password: str
    confirm_password: str
    contact: str


class LoginRequest(BaseModel):
    email: str
    password: str


@router.post("/register")
def register(req: RegisterRequest):
    name = req.name.strip()
    email = req.email.strip().lower()
    contact = req.contact.strip()

    if len(name) < 3:
        raise HTTPException(400, "Name must be at least 3 characters.")
    if not EMAIL_RE.match(email):
        raise HTTPException(400, "Enter a valid email address.")
    if len(req.password) < 8:
        raise HTTPException(400, "Password must be at least 8 characters.")
    if req.password != req.confirm_password:
        raise HTTPException(400, "Passwords do not match.")
    if not contact.isdigit() or len(contact) != 10:
        raise HTTPException(400, "Enter a valid 10-digit contact number.")

    db = get_db()
    try:
        existing = db.execute("SELECT user_id FROM users WHERE email = ?", (email,)).fetchone()
        if existing:
            raise HTTPException(400, "This email is already in use.")

        cursor = db.execute(
            "INSERT INTO users (name, email, password_hash, contact, is_admin) VALUES (?, ?, ?, ?, 0)",
            (name, email, hash_password(req.password), contact),
        )
        db.commit()
        user_id = cursor.lastrowid
        # Create freelancer_stats row
        db.execute(
            "INSERT OR IGNORE INTO freelancer_stats (freelancer_id) VALUES (?)", (user_id,)
        )
        db.commit()
        token = create_token(user_id)
        return {"token": token, "user_id": user_id, "name": name, "is_admin": 0}
    finally:
        db.close()


@router.post("/login")
def login(req: LoginRequest):
    email = req.email.strip().lower()
    if not email or not req.password:
        raise HTTPException(400, "Email and password are required.")
    if not EMAIL_RE.match(email):
        raise HTTPException(400, "Enter a valid email address.")

    db = get_db()
    try:
        user = db.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
        if not user or not verify_password(req.password, user["password_hash"]):
            raise HTTPException(401, "Incorrect email or password.")
        token = create_token(user["user_id"])
        return {
            "token": token,
            "user_id": user["user_id"],
            "name": user["name"],
            "wallet_balance": user["wallet_balance"],
            "is_admin": user["is_admin"],
        }
    finally:
        db.close()


@router.get("/me")
def get_me(user_id: int = Depends(get_current_user_id)):
    db = get_db()
    try:
        user = db.execute(
            "SELECT user_id, name, email, contact, wallet_balance, join_date, is_admin FROM users WHERE user_id = ?",
            (user_id,),
        ).fetchone()
        if not user:
            raise HTTPException(404, "User not found.")
        return dict(user)
    finally:
        db.close()


@router.get("/categories")
def get_categories():
    db = get_db()
    try:
        rows = db.execute("SELECT * FROM categories ORDER BY category_name").fetchall()
        return [dict(r) for r in rows]
    finally:
        db.close()
