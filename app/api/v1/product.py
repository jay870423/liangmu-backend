"""商品模块API"""
from fastapi import APIRouter, Query
from app.utils.response import success_response, error_response, page_response
from app.database import get_db_cursor

router = APIRouter()

@router.get("/products/{product_id}")
async def get_product_detail(product_id: str):
    with get_db_cursor() as cursor:
        cursor.execute("""
            SELECT id, category_id, name, subtitle, description, price, original_price, stock, images, detail_images, specs, tags, sales_count, rating
            FROM products WHERE id = %s AND is_on_sale = true
        """, (product_id,))
        product = cursor.fetchone()
        if not product:
            return error_response(2001, "商品不存在")
    images = product["images"] or []
    return success_response(data={
        "id": str(product["id"]), "name": product["name"], "subtitle": product["subtitle"] or "",
        "description": product["description"] or "", "price": int(product["price"]),
        "original_price": int(product["original_price"]) if product["original_price"] else 0,
        "stock": product["stock"] or 0, "main_image": images[0] if images else "",
        "images": images, "detail_images": product["detail_images"] or [],
        "specs": product["specs"] or [], "tags": product["tags"] or [],
        "sales": product["sales_count"] or 0, "rating": float(product["rating"]) if product["rating"] else 5.0,
        "is_favorite": False
    })

@router.get("/products")
async def list_products(category_id: str = "", page: int = 1, page_size: int = 20):
    offset = (page - 1) * page_size
    with get_db_cursor() as cursor:
        if category_id:
            cursor.execute("""
                SELECT id, name, subtitle, price, original_price, images, sales_count, rating
                FROM products WHERE is_on_sale = true AND category_id = %s
                ORDER BY created_at DESC LIMIT %s OFFSET %s
            """, (category_id, page_size, offset))
            products = cursor.fetchall()
            cursor.execute("SELECT COUNT(*) as total FROM products WHERE is_on_sale = true AND category_id = %s", (category_id,))
        else:
            cursor.execute("""
                SELECT id, name, subtitle, price, original_price, images, sales_count, rating
                FROM products WHERE is_on_sale = true
                ORDER BY created_at DESC LIMIT %s OFFSET %s
            """, (page_size, offset))
            products = cursor.fetchall()
            cursor.execute("SELECT COUNT(*) as total FROM products WHERE is_on_sale = true")
        total = cursor.fetchone()["total"]
    items = []
    for p in products:
        images = p["images"] or []
        items.append({
            "id": str(p["id"]), "name": p["name"], "subtitle": p["subtitle"] or "",
            "price": int(p["price"]), "original_price": int(p["original_price"]) if p["original_price"] else 0,
            "main_image": images[0] if images else "", "sales": p["sales_count"] or 0,
            "rating": float(p["rating"]) if p["rating"] else 5.0
        })
    return success_response(data=page_response(items, total, page, page_size))

@router.get("/products/search")
async def search_products(keyword: str, page: int = 1, page_size: int = 20):
    offset = (page - 1) * page_size
    pattern = f"%{keyword}%"
    with get_db_cursor() as cursor:
        cursor.execute("""
            SELECT id, name, subtitle, price, original_price, images, sales_count, rating
            FROM products WHERE is_on_sale = true AND (name LIKE %s OR subtitle LIKE %s OR description LIKE %s)
            ORDER BY sales_count DESC LIMIT %s OFFSET %s
        """, (pattern, pattern, pattern, page_size, offset))
        products = cursor.fetchall()
        cursor.execute("SELECT COUNT(*) as total FROM products WHERE is_on_sale = true AND (name LIKE %s OR subtitle LIKE %s OR description LIKE %s)", (pattern, pattern, pattern))
        total = cursor.fetchone()["total"]
    items = []
    for p in products:
        images = p["images"] or []
        items.append({
            "id": str(p["id"]), "name": p["name"], "subtitle": p["subtitle"] or "",
            "price": int(p["price"]), "original_price": int(p["original_price"]) if p["original_price"] else 0,
            "main_image": images[0] if images else "", "sales": p["sales_count"] or 0,
            "rating": float(p["rating"]) if p["rating"] else 5.0
        })
    return success_response(data=page_response(items, total, page, page_size))
