"""商品模块API"""
from decimal import Decimal, ROUND_HALF_UP
from fastapi import APIRouter, Query
from app.utils.response import success_response, error_response, page_response
from app.database import get_db_cursor

router = APIRouter()

def money(value):
    amount = Decimal(str(value or 0)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return f"{amount:.2f}"

def build_search_filter(keyword: str):
    terms = [term.strip() for term in keyword.split() if term.strip()]
    if not terms:
        return "WHERE p.is_on_sale = true AND false", []

    fields = (
        "COALESCE(p.name, '') ILIKE %s OR "
        "COALESCE(p.subtitle, '') ILIKE %s OR "
        "COALESCE(p.description, '') ILIKE %s OR "
        "COALESCE(p.tags::text, '') ILIKE %s OR "
        "COALESCE(c.name, '') ILIKE %s"
    )
    conditions = []
    params = []
    for term in terms:
        pattern = f"%{term}%"
        conditions.append(f"({fields})")
        params.extend([pattern, pattern, pattern, pattern, pattern])

    return f"WHERE p.is_on_sale = true AND {' AND '.join(conditions)}", params

@router.get("/products/search")
async def search_products(keyword: str = "", page: int = 1, page_size: int = 20):
    offset = (page - 1) * page_size
    where, params = build_search_filter(keyword.strip())
    with get_db_cursor() as cursor:
        cursor.execute(f"""
            SELECT p.id, p.name, p.subtitle, p.price, p.original_price, p.shipping_fee, p.images, p.sales_count, p.rating
            FROM products p
            LEFT JOIN categories c ON p.category_id = c.id
            {where}
            ORDER BY p.sales_count DESC, p.created_at DESC LIMIT %s OFFSET %s
        """, params + [page_size, offset])
        products = cursor.fetchall()
        cursor.execute(f"""
            SELECT COUNT(*) as total
            FROM products p
            LEFT JOIN categories c ON p.category_id = c.id
            {where}
        """, params)
        total = cursor.fetchone()["total"]
    items = []
    for p in products:
        images = p["images"] or []
        items.append({
            "id": str(p["id"]), "name": p["name"], "subtitle": p["subtitle"] or "",
            "price": money(p["price"]), "original_price": money(p["original_price"]),
            "shipping_fee": money(p["shipping_fee"]),
            "main_image": images[0] if images else "", "sales": p["sales_count"] or 0,
            "rating": float(p["rating"]) if p["rating"] else 5.0
        })
    return success_response(data=page_response(items, total, page, page_size))

@router.get("/products/{product_id}")
async def get_product_detail(product_id: str):
    with get_db_cursor() as cursor:
        cursor.execute("""
            SELECT id, category_id, name, subtitle, description, price, original_price, shipping_fee, stock, images, detail_images, specs, tags, sales_count, rating
            FROM products WHERE id = %s AND is_on_sale = true
        """, (product_id,))
        product = cursor.fetchone()
        if not product:
            return error_response(2001, "商品不存在")
    images = product["images"] or []
    return success_response(data={
        "id": str(product["id"]), "name": product["name"], "subtitle": product["subtitle"] or "",
        "description": product["description"] or "", "price": money(product["price"]),
        "original_price": money(product["original_price"]),
        "shipping_fee": money(product["shipping_fee"]),
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
                SELECT id, name, subtitle, price, original_price, shipping_fee, images, sales_count, rating
                FROM products WHERE is_on_sale = true AND category_id = %s
                ORDER BY created_at DESC LIMIT %s OFFSET %s
            """, (category_id, page_size, offset))
            products = cursor.fetchall()
            cursor.execute("SELECT COUNT(*) as total FROM products WHERE is_on_sale = true AND category_id = %s", (category_id,))
        else:
            cursor.execute("""
                SELECT id, name, subtitle, price, original_price, shipping_fee, images, sales_count, rating
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
            "price": money(p["price"]), "original_price": money(p["original_price"]),
            "shipping_fee": money(p["shipping_fee"]),
            "main_image": images[0] if images else "", "sales": p["sales_count"] or 0,
            "rating": float(p["rating"]) if p["rating"] else 5.0
        })
    return success_response(data=page_response(items, total, page, page_size))

