from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, List
import uuid

router = APIRouter(prefix="/admin/products", tags=["admin-product"])

class ProductCreate(BaseModel):
    category_id: Optional[str] = None
    name: str
    subtitle: str = ""
    description: str = ""
    price: float = 0
    original_price: float = 0
    shipping_fee: float = 0
    images: List[str] = []
    stock: int = 0
    rating: float = 5.0
    is_on_sale: bool = True

class ProductUpdate(BaseModel):
    category_id: Optional[str] = None
    name: Optional[str] = None
    subtitle: Optional[str] = None
    description: Optional[str] = None
    price: Optional[float] = None
    original_price: Optional[float] = None
    shipping_fee: Optional[float] = None
    images: Optional[List[str]] = None
    stock: Optional[int] = None
    rating: Optional[float] = None
    is_on_sale: Optional[bool] = None

def normalize_rating(rating: float) -> float:
    if rating is None:
        return 5.0
    return min(5.0, max(1.0, round(float(rating), 1)))

@router.get("/")
async def list_products(page: int = 1, page_size: int = 10, keyword: str = None, category_id: str = None):
    from app.database import get_db_cursor
    offset = (page - 1) * page_size
    with get_db_cursor() as cur:
        conditions = []
        params = []
        if keyword and keyword.strip():
            like = f"%{keyword.strip()}%"
            conditions.append("(p.name ILIKE %s OR COALESCE(p.subtitle, '') ILIKE %s OR COALESCE(c.name, '') ILIKE %s)")
            params.extend([like, like, like])
        if category_id:
            conditions.append("p.category_id = %s")
            params.append(category_id)
        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        cur.execute(f"""SELECT COUNT(*) FROM products p
                        LEFT JOIN categories c ON p.category_id = c.id
                        {where}""", params)
        total = cur.fetchone()["count"]
        list_params = params + [page_size, offset]
        cur.execute(f"""SELECT p.*, c.name as category_name
                        FROM products p LEFT JOIN categories c ON p.category_id = c.id
                        {where} ORDER BY p.created_at DESC LIMIT %s OFFSET %s""", list_params)
        rows = cur.fetchall()
        items = [{
            "id": str(r["id"]), "category_id": str(r["category_id"]) if r["category_id"] else "",
            "category_name": r["category_name"] or "",
            "name": r["name"], "subtitle": r["subtitle"] or "",
            "description": r["description"] or "",
            "price": float(r["price"]), "original_price": float(r["original_price"]),
            "shipping_fee": float(r["shipping_fee"] or 0),
            "images": r["images"] if isinstance(r["images"], list) else [],
            "stock": r["stock"], "sales_count": r["sales_count"] or 0,
            "rating": float(r["rating"] or 0),
            "is_on_sale": r["is_on_sale"],
            "created_at": r["created_at"].isoformat() if r["created_at"] else ""
        } for r in rows]
        return {"items": items, "total": total}

@router.get("/{product_id}")
async def get_product(product_id: str):
    from app.database import get_db_cursor
    with get_db_cursor() as cur:
        cur.execute("""SELECT p.*, c.name as category_name FROM products p
                       LEFT JOIN categories c ON p.category_id = c.id WHERE p.id = %s""", (product_id,))
        r = cur.fetchone()
        if not r:
            raise HTTPException(status_code=404, detail="商品不存在")
        return {
            "id": str(r["id"]), "category_id": str(r["category_id"]) if r["category_id"] else "",
            "category_name": r["category_name"] or "",
            "name": r["name"], "subtitle": r["subtitle"] or "",
            "description": r["description"] or "",
            "price": float(r["price"]), "original_price": float(r["original_price"]),
            "shipping_fee": float(r["shipping_fee"] or 0),
            "images": r["images"] if isinstance(r["images"], list) else [],
            "stock": r["stock"], "sales_count": r["sales_count"] or 0,
            "rating": float(r["rating"] or 0), "is_on_sale": r["is_on_sale"],
            "created_at": r["created_at"].isoformat() if r["created_at"] else ""
        }

@router.post("/")
async def create_product(req: ProductCreate):
    from app.database import get_db_cursor
    import json
    product_id = str(uuid.uuid4())
    images_json = json.dumps(req.images) if req.images else "[]"
    rating = normalize_rating(req.rating)
    with get_db_cursor() as cur:
        cur.execute("""INSERT INTO products (id, category_id, name, subtitle, description, price, original_price, shipping_fee, images, stock, rating, is_on_sale)
                       VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s, %s, %s)""",
                    (product_id, req.category_id, req.name, req.subtitle, req.description,
                     req.price, req.original_price, req.shipping_fee, images_json, req.stock, rating, req.is_on_sale))
    return {"id": product_id, "message": "创建成功"}

@router.put("/{product_id}")
async def update_product(product_id: str, req: ProductUpdate):
    from app.database import get_db_cursor
    import json
    with get_db_cursor() as cur:
        cur.execute("SELECT id FROM products WHERE id = %s", (product_id,))
        if not cur.fetchone():
            raise HTTPException(status_code=404, detail="商品不存在")
        updates = []
        vals = []
        if req.category_id is not None: updates.append("category_id=%s"); vals.append(req.category_id)
        if req.name is not None: updates.append("name=%s"); vals.append(req.name)
        if req.subtitle is not None: updates.append("subtitle=%s"); vals.append(req.subtitle)
        if req.description is not None: updates.append("description=%s"); vals.append(req.description)
        if req.price is not None: updates.append("price=%s"); vals.append(req.price)
        if req.original_price is not None: updates.append("original_price=%s"); vals.append(req.original_price)
        if req.shipping_fee is not None: updates.append("shipping_fee=%s"); vals.append(req.shipping_fee)
        if req.images is not None: updates.append("images=%s::jsonb"); vals.append(json.dumps(req.images))
        if req.stock is not None: updates.append("stock=%s"); vals.append(req.stock)
        if req.rating is not None: updates.append("rating=%s"); vals.append(normalize_rating(req.rating))
        if req.is_on_sale is not None: updates.append("is_on_sale=%s"); vals.append(req.is_on_sale)
        if updates:
            vals.append(product_id)
            cur.execute(f"UPDATE products SET {', '.join(updates)} WHERE id = %s", vals)
    return {"message": "更新成功"}

@router.delete("/{product_id}")
async def delete_product(product_id: str):
    from app.database import get_db_cursor
    with get_db_cursor() as cur:
        cur.execute("DELETE FROM products WHERE id = %s", (product_id,))
    return {"message": "删除成功"}

@router.post("/{product_id}/toggle")
async def toggle_product(product_id: str):
    from app.database import get_db_cursor
    with get_db_cursor() as cur:
        cur.execute("UPDATE products SET is_on_sale = NOT is_on_sale WHERE id = %s RETURNING is_on_sale", (product_id,))
        r = cur.fetchone()
        if not r:
            raise HTTPException(status_code=404, detail="商品不存在")
    return {"is_on_sale": r["is_on_sale"], "message": "操作成功"}
