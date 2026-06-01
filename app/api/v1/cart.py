"""购物车模块API"""
from fastapi import APIRouter, Depends, Request
from app.api.deps import get_current_user
from app.utils.response import success_response, error_response
from app.database import get_db_cursor, get_db
import uuid
import json

router = APIRouter()

@router.get("/cart")
async def get_cart(user: dict = Depends(get_current_user)):
    user_id = user["user_id"]
    with get_db_cursor() as cursor:
        cursor.execute("SELECT ci.id, ci.product_id, ci.quantity, ci.sku_spec, p.name as product_name, p.price, p.images, p.stock FROM cart_items ci JOIN products p ON ci.product_id = p.id WHERE ci.user_id = %s ORDER BY ci.created_at DESC", (user_id,))
        items = cursor.fetchall()
    result_items = []
    total_amount = 0.0
    total_count = 0
    for item in items:
        images = item["images"] or []
        price = float(item["price"]) if item["price"] else 0.0
        quantity = item["quantity"] or 1
        subtotal = price * quantity
        result_items.append({"id": str(item["id"]), "product_id": str(item["product_id"]), "product_name": item["product_name"], "product_image": images[0] if images else "", "sku_spec": item["sku_spec"] or {}, "price": str(item["price"]), "quantity": quantity, "subtotal": f"{subtotal:.2f}", "stock": item["stock"] or 0})
        total_amount += subtotal
        total_count += quantity
    return success_response(data={"items": result_items, "total_amount": f"{total_amount:.2f}", "total_count": total_count})

@router.post("/cart")
async def add_to_cart(req: Request, user: dict = Depends(get_current_user)):
    user_id = user["user_id"]
    body = await req.json()
    product_id = body.get("product_id")
    quantity = body.get("quantity", 1)
    sku_spec = body.get("sku_spec", {})
    if not product_id:
        return error_response(1001, "缺少商品ID")
    with get_db_cursor() as cursor:
        cursor.execute("SELECT id, stock FROM products WHERE id = %s AND is_on_sale = true", (product_id,))
        product = cursor.fetchone()
    if not product:
        return error_response(2001, "商品不存在")
    if product["stock"] < quantity:
        return error_response(2002, "库存不足")
    sku_spec_json = json.dumps(sku_spec, sort_keys=True)
    with get_db_cursor() as cursor:
        cursor.execute("SELECT id, quantity FROM cart_items WHERE user_id = %s AND product_id = %s AND sku_spec = %s::jsonb", (user_id, product_id, sku_spec_json))
        existing = cursor.fetchone()
    if existing:
        new_qty = existing["quantity"] + quantity
        if new_qty > product["stock"]:
            return error_response(2002, "库存不足")
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("UPDATE cart_items SET quantity = %s WHERE id = %s", (new_qty, str(existing["id"])))
            conn.commit()
    else:
        cart_id = str(uuid.uuid4())
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("INSERT INTO cart_items (id, user_id, product_id, quantity, sku_spec) VALUES (%s, %s, %s, %s, %s::jsonb)", (cart_id, user_id, product_id, quantity, sku_spec_json))
            conn.commit()
    return success_response(message="添加成功")

@router.put("/cart/{cart_item_id}")
async def update_cart_item(cart_item_id: str, req: Request, user: dict = Depends(get_current_user)):
    user_id = user["user_id"]
    body = await req.json()
    quantity = body.get("quantity", 1)
    if quantity < 1:
        return error_response(1000, "数量必须大于0")
    with get_db_cursor() as cursor:
        cursor.execute("SELECT ci.id, p.stock FROM cart_items ci JOIN products p ON ci.product_id = p.id WHERE ci.id = %s AND ci.user_id = %s", (cart_item_id, user_id))
        item = cursor.fetchone()
    if not item:
        return error_response(1000, "购物车项不存在")
    if item["stock"] < quantity:
        return error_response(2002, "库存不足")
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE cart_items SET quantity = %s WHERE id = %s", (quantity, cart_item_id))
        conn.commit()
    return success_response(message="更新成功")

@router.delete("/cart/{cart_item_id}")
async def remove_from_cart(cart_item_id: str, user: dict = Depends(get_current_user)):
    user_id = user["user_id"]
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM cart_items WHERE id = %s AND user_id = %s", (cart_item_id, user_id))
        conn.commit()
    return success_response(message="删除成功")

@router.delete("/cart")
async def clear_cart(user: dict = Depends(get_current_user)):
    user_id = user["user_id"]
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM cart_items WHERE user_id = %s", (user_id,))
        conn.commit()
    return success_response(message="清空成功")
