from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from backend.database import get_db
from backend.auth_utils import get_current_user_id

router = APIRouter()


class CreateServiceRequest(BaseModel):
    category_id: int
    title: str
    base_price: float
    description: str = ""


@router.get("")
def list_services(user_id: int = Depends(get_current_user_id)):
    db = get_db()
    try:
        rows = db.execute(
            """SELECT s.*, c.category_name FROM services s
               LEFT JOIN categories c ON s.category_id = c.category_id
               WHERE s.user_id = ? ORDER BY s.created_date DESC""",
            (user_id,),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        db.close()


@router.post("")
def create_service(req: CreateServiceRequest, user_id: int = Depends(get_current_user_id)):
    title = req.title.strip()
    if not title:
        raise HTTPException(400, "Service title is required.")
    if req.base_price <= 0:
        raise HTTPException(400, "Base price must be greater than zero.")

    db = get_db()
    try:
        active_count = db.execute(
            "SELECT COUNT(*) FROM services WHERE user_id = ? AND active_status = 'Y'", (user_id,)
        ).fetchone()[0]
        if active_count >= 2:
            raise HTTPException(400, "You can only list up to 2 active services at a time.")

        cursor = db.execute(
            "INSERT INTO services (user_id, category_id, title, base_price, description) VALUES (?,?,?,?,?)",
            (user_id, req.category_id, title, req.base_price, req.description.strip()),
        )
        db.commit()
        return {"service_id": cursor.lastrowid, "message": "Service created successfully."}
    finally:
        db.close()


@router.put("/{service_id}/deactivate")
def deactivate_service(service_id: int, user_id: int = Depends(get_current_user_id)):
    db = get_db()
    try:
        service = db.execute("SELECT * FROM services WHERE service_id = ?", (service_id,)).fetchone()
        if not service:
            raise HTTPException(404, "Service not found.")
        if service["user_id"] != user_id:
            raise HTTPException(403, "You can only manage your own services.")
        if service["active_status"] == "N":
            raise HTTPException(400, "Service is already inactive.")

        db.execute(
            "UPDATE services SET active_status = 'N' WHERE service_id = ?", (service_id,)
        )
        db.commit()
        return {"message": "Service deactivated."}
    finally:
        db.close()
