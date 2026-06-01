"""分类模块API"""
from fastapi import APIRouter, Depends, Request
from app.api.deps import get_current_user
from app.utils.response import success_response, error_response, page_response
from app.database import get_db_cursor

router = APIRouter()

@router.get("/categories")
async def get_categories():
    with get_db_cursor() as cursor:
        cursor.execute("SELECT id, name, icon_url, sort_order FROM categories WHERE is_active = true ORDER BY sort_order ASC")
        categories = cursor.fetchall()
    items = [{"id": str(c["id"]), "name": c["name"], "icon_url": c["icon_url"] or "", "sort_order": c["sort_order"]} for c in categories]
    return success_response(data={"items": items})

@router.get("/categories/{category_id}/products")
async def get_category_products(category_id: str, page: int = 1, page_size: int = 20):
    offset = (page - 1) * page_size
    with get_db_cursor() as cursor:
        cursor.execute("""
            SELECT id, name, subtitle, price, original_price, images, sales_count, rating
            FROM products WHERE category_id = %s AND is_on_sale = true
            ORDER BY created_at DESC LIMIT %s OFFSET %s
        """, (category_id, page_size, offset))
        products = cursor.fetchall()
        cursor.execute("SELECT COUNT(*) as total FROM products WHERE category_id = %s AND is_on_sale = true", (category_id,))
        total = cursor.fetchone()["total"]
    items = []
    for p in products:
        images = p["images"] or []
        items.append({
            "id": str(p["id"]), "name": p["name"], "subtitle": p["subtitle"] or "",
            "price": str(p["price"]), "original_price": str(p["original_price"]) if p["original_price"] else "0.00",
            "image": images[0] if images else "", "sales_count": p["sales_count"] or 0,
            "rating": float(p["rating"]) if p["rating"] else 5.0
        })
    return success_response(data=page_response(items, total, page, page_size))
