"""积分模块API"""
from fastapi import APIRouter, Depends
from app.api.deps import get_current_user
from app.utils.response import success_response, page_response
from app.database import get_db_cursor

router = APIRouter()

@router.get("/points/log")
async def get_points_log(user: dict = Depends(get_current_user), page: int = 1, page_size: int = 20):
    user_id = user["user_id"]
    offset = (page - 1) * page_size
    with get_db_cursor() as cursor:
        cursor.execute("""
            SELECT id, type, points, balance, note, created_at
            FROM points_log WHERE user_id = %s
            ORDER BY created_at DESC LIMIT %s OFFSET %s
        """, (user_id, page_size, offset))
        items = cursor.fetchall()
        cursor.execute("SELECT COUNT(*) as total FROM points_log WHERE user_id = %s", (user_id,))
        total = cursor.fetchone()["total"]
    result_items = []
    for item in items:
        result_items.append({
            "id": str(item["id"]), "type": item["type"],
            "points": item["points"], "balance": item["balance"],
            "note": item["note"] or "", "created_at": item["created_at"].isoformat() if item["created_at"] else None
        })
    return success_response(data=page_response(result_items, total, page, page_size))
