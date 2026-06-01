"""收藏模块API"""
from fastapi import APIRouter, Depends, Request
from app.api.deps import get_current_user
from app.utils.response import success_response, error_response, page_response
from app.database import get_db_cursor, get_db
import uuid

router = APIRouter()

@router.get("/favorites")
async def get_favorites(user: dict = Depends(get_current_user), page: int = 1, page_size: int = 20):
    user_id = user["user_id"]
    offset = (page - 1) * page_size
    with get_db_cursor() as cursor:
        cursor.execute("""
            SELECT f.id as favorite_id, p.id, p.name, p.subtitle, p.price, p.original_price, p.images, p.sales_count, p.rating
            FROM favorites f JOIN products p ON f.product_id = p.id
            WHERE f.user_id = %s ORDER BY f.created_at DESC LIMIT %s OFFSET %s
        """, (user_id, page_size, offset))
        items = cursor.fetchall()
        cursor.execute("SELECT COUNT(*) as total FROM favorites WHERE user_id = %s", (user_id,))
        total = cursor.fetchone()["total"]
    result_items = []
    for item in items:
        images = item["images"] or []
        result_items.append({
            "id": str(item["id"]), "favorite_id": str(item["favorite_id"]),
            "name": item["name"], "subtitle": item["subtitle"] or "",
            "price": str(item["price"]), "original_price": str(item["original_price"]) if item["original_price"] else "0.00",
            "image": images[0] if images else "", "sales_count": item["sales_count"] or 0,
            "rating": float(item["rating"]) if item["rating"] else 5.0
        })
    return success_response(data=page_response(result_items, total, page, page_size))

@router.post("/favorites")
async def add_favorite(req: Request, user: dict = Depends(get_current_user)):
    user_id = user["user_id"]
    body = await req.json()
    product_id = body.get("product_id")
    if not product_id:
        return error_response(1001, "缺少商品ID")
    with get_db_cursor() as cursor:
        cursor.execute("SELECT id FROM products WHERE id = %s", (product_id,))
        if not cursor.fetchone():
            return error_response(2001, "商品不存在")
        cursor.execute("SELECT id FROM favorites WHERE user_id = %s AND product_id = %s", (user_id, product_id))
        if cursor.fetchone():
            return error_response(1000, "已收藏该商品")
    favorite_id = str(uuid.uuid4())
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("INSERT INTO favorites (id, user_id, product_id) VALUES (%s, %s, %s)", (favorite_id, user_id, product_id))
        conn.commit()
    return success_response(data={"favorite_id": favorite_id}, message="收藏成功")

@router.delete("/favorites/{favorite_id}")
async def remove_favorite(favorite_id: str, user: dict = Depends(get_current_user)):
    user_id = user["user_id"]
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM favorites WHERE id = %s AND user_id = %s", (favorite_id, user_id))
        conn.commit()
    return success_response(message="取消收藏成功")
