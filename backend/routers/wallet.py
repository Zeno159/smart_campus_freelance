from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from backend.database import get_db
from backend.auth_utils import get_current_user_id

router = APIRouter()


class WalletRequest(BaseModel):
    amount: float


@router.post("/topup")
def topup(req: WalletRequest, user_id: int = Depends(get_current_user_id)):
    if req.amount <= 0:
        raise HTTPException(400, "Amount must be a positive number.")

    db = get_db()
    try:
        db.execute(
            "UPDATE users SET wallet_balance = wallet_balance + ? WHERE user_id = ?",
            (req.amount, user_id),
        )
        db.execute(
            "INSERT INTO wallet_transactions (user_id, amount, txn_type, description) VALUES (?,?,'credit','Wallet top-up')",
            (user_id, req.amount),
        )
        db.commit()
        user = db.execute("SELECT wallet_balance FROM users WHERE user_id = ?", (user_id,)).fetchone()
        return {"wallet_balance": user["wallet_balance"], "message": f"Rs.{req.amount:.2f} added to your wallet."}
    finally:
        db.close()


@router.post("/withdraw")
def withdraw(req: WalletRequest, user_id: int = Depends(get_current_user_id)):
    if req.amount <= 0:
        raise HTTPException(400, "Amount must be a positive number.")

    db = get_db()
    try:
        user = db.execute("SELECT wallet_balance FROM users WHERE user_id = ?", (user_id,)).fetchone()
        if user["wallet_balance"] < req.amount:
            raise HTTPException(
                400,
                f"Insufficient balance. Your current balance is Rs.{user['wallet_balance']:.2f}.",
            )
        db.execute(
            "UPDATE users SET wallet_balance = wallet_balance - ? WHERE user_id = ?",
            (req.amount, user_id),
        )
        db.execute(
            "INSERT INTO wallet_transactions (user_id, amount, txn_type, description) VALUES (?,?,'debit','Wallet withdrawal')",
            (user_id, req.amount),
        )
        db.commit()
        user = db.execute("SELECT wallet_balance FROM users WHERE user_id = ?", (user_id,)).fetchone()
        return {"wallet_balance": user["wallet_balance"], "message": f"Rs.{req.amount:.2f} withdrawn successfully."}
    finally:
        db.close()


@router.get("/transactions")
def get_transactions(user_id: int = Depends(get_current_user_id)):
    db = get_db()
    try:
        rows = db.execute(
            "SELECT * FROM wallet_transactions WHERE user_id = ? ORDER BY txn_date DESC LIMIT 50",
            (user_id,),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        db.close()
