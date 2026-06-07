from datetime import datetime
import json
import random
import uuid

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from psycopg2.extras import RealDictCursor

from app.api.deps import get_current_user
from app.database import get_db, get_db_cursor
from app.services.wechat_pay import (
    WechatPayError,
    amount_to_fen,
    decrypt_notify_resource,
    jsapi_prepay,
    verify_notify_signature,
)
from app.utils.response import error_response, page_response, success_response


router = APIRouter()


def generate_order_no():
    return f"LM{datetime.now().strftime('%Y%m%d%H%M%S')}{random.randint(100000, 999999)}"


class OrderCreateError(Exception):
    def __init__(self, code: int, message: str):
        self.code = code
        self.message = message
        super().__init__(message)


@router.post("/orders")
async def create_order(req: Request, user: dict = Depends(get_current_user)):
    user_id = user["user_id"]
    body = await req.json()
    address_id = body.get("address_id")
    delivery_type = body.get("delivery_type", "express")
    coupon_id = body.get("coupon_id")
    use_points = body.get("use_points", 0)

    try:
        use_points = int(use_points or 0)
    except (TypeError, ValueError):
        return error_response(1000, "积分数量不正确")
    if use_points < 0:
        return error_response(1000, "积分数量不正确")

    items_data = body.get("items", [])
    if not items_data:
        return error_response(1001, "缺少商品信息")

    normalized_items = []
    product_quantities = {}
    for item_data in items_data:
        product_id = str(item_data.get("product_id") or "").strip()
        try:
            quantity = int(item_data.get("quantity", 1))
        except (TypeError, ValueError):
            return error_response(1001, "商品数量不正确")
        if not product_id:
            return error_response(1001, "缺少商品ID")
        if quantity <= 0:
            return error_response(1001, "商品数量必须大于0")
        sku_spec = item_data.get("sku_spec", {})
        normalized_items.append({"product_id": product_id, "quantity": quantity, "sku_spec": sku_spec})
        product_quantities[product_id] = product_quantities.get(product_id, 0) + quantity

    receiver_name = ""
    receiver_phone = ""
    shipping_address = ""
    if address_id:
        with get_db_cursor() as cursor:
            cursor.execute(
                "SELECT receiver_name, phone, province, city, district, detail_address FROM addresses WHERE id = %s AND user_id = %s",
                (address_id, user_id),
            )
            addr = cursor.fetchone()
        if not addr:
            return error_response(2005, "收货地址不存在")
        receiver_name = addr["receiver_name"] or ""
        receiver_phone = addr["phone"] or ""
        shipping_address = f"{addr['province']}{addr['city']}{addr['district']}{addr['detail_address']}"

    order_no = generate_order_no()
    order_id = str(uuid.uuid4())
    total_amount = 0.0
    freight_amount = 0.0
    coupon_amount = 0.0
    points_amount = 0.0
    pay_amount = 0.0

    try:
        with get_db() as conn:
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            products = {}

            for product_id in sorted(product_quantities.keys()):
                cursor.execute(
                    "SELECT id, name, price, stock, images FROM products WHERE id = %s AND is_on_sale = true FOR UPDATE",
                    (product_id,),
                )
                product = cursor.fetchone()
                if not product:
                    raise OrderCreateError(2001, f"商品不存在: {product_id}")
                required_quantity = product_quantities[product_id]
                if product["stock"] < required_quantity:
                    raise OrderCreateError(2002, f"库存不足: {product['name']}")
                products[product_id] = product

            order_items = []
            for item_data in normalized_items:
                product = products[item_data["product_id"]]
                images = product["images"] or []
                quantity = item_data["quantity"]
                subtotal = float(product["price"]) * quantity
                total_amount += subtotal
                order_items.append({
                    "product_id": str(product["id"]),
                    "product_name": product["name"],
                    "product_image": images[0] if images else "",
                    "sku_spec": item_data["sku_spec"],
                    "price": product["price"],
                    "quantity": quantity,
                    "subtotal": subtotal,
                })

            freight_amount = 0.0 if total_amount >= 500 else 10.0
            if coupon_id:
                cursor.execute("""
                    SELECT uc.id AS user_coupon_id, c.discount_amount, c.min_order_amount
                    FROM user_coupons uc
                    JOIN coupons c ON c.id = uc.coupon_id
                    WHERE c.id = %s AND uc.user_id = %s AND uc.status = 'unused' AND c.end_time > %s
                    FOR UPDATE OF uc
                """, (coupon_id, user_id, datetime.now()))
                coupon = cursor.fetchone()
                if not coupon:
                    raise OrderCreateError(2004, "优惠券不可用")
                if total_amount < float(coupon["min_order_amount"]):
                    raise OrderCreateError(2004, f"订单金额未达门槛: {coupon['min_order_amount']}元")
                coupon_amount = float(coupon["discount_amount"])

            points_used = 0
            available_points = 0
            if use_points > 0:
                cursor.execute("SELECT available_points FROM users WHERE id = %s FOR UPDATE", (user_id,))
                user_data = cursor.fetchone()
                available_points = user_data["available_points"] if user_data else 0
                if use_points > available_points:
                    raise OrderCreateError(1000, "积分不足")
                points_used = use_points
                points_amount = points_used / 100.0

            pay_amount = max(total_amount + freight_amount - coupon_amount - points_amount, 0)

            cursor.execute("""
                INSERT INTO orders (
                    id, order_no, user_id, address_id, receiver_name, receiver_phone, shipping_address,
                    total_amount, freight_amount, coupon_amount, points_amount, pay_amount,
                    points_earned, points_used, delivery_type, status, buyer_note, created_at, updated_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
            """, (
                order_id, order_no, user_id, address_id, receiver_name, receiver_phone, shipping_address,
                total_amount, freight_amount, coupon_amount, points_amount, pay_amount,
                int(total_amount), points_used, delivery_type, "pending", body.get("buyer_note", ""), datetime.now(),
            ))

            for item in order_items:
                cursor.execute("""
                    INSERT INTO order_items (id, order_id, product_id, product_name, product_image, sku_spec, price, quantity, subtotal)
                    VALUES (%s, %s, %s, %s, %s, %s::jsonb, %s, %s, %s)
                """, (
                    str(uuid.uuid4()), order_id, item["product_id"], item["product_name"], item["product_image"],
                    json.dumps(item["sku_spec"], ensure_ascii=False), item["price"], item["quantity"], item["subtotal"],
                ))

            for product_id, quantity in product_quantities.items():
                cursor.execute("""
                    UPDATE products
                    SET stock = stock - %s, sales_count = sales_count + %s, updated_at = NOW()
                    WHERE id = %s AND stock >= %s
                """, (quantity, quantity, product_id, quantity))
                if cursor.rowcount != 1:
                    raise OrderCreateError(2002, "库存不足，请重新下单")

            if coupon_id:
                cursor.execute(
                    "UPDATE user_coupons SET status = 'used', order_id = %s, used_at = %s WHERE user_id = %s AND coupon_id = %s AND status = 'unused'",
                    (order_id, datetime.now(), user_id, coupon_id),
                )
                if cursor.rowcount != 1:
                    raise OrderCreateError(2004, "优惠券不可用")

            if points_used > 0:
                cursor.execute("UPDATE users SET available_points = available_points - %s WHERE id = %s", (points_used, user_id))
                cursor.execute("""
                    INSERT INTO points_log (id, user_id, order_id, type, points, balance, note, created_at)
                    VALUES (%s, %s, %s, 'redeem', %s, %s, %s, %s)
                """, (
                    str(uuid.uuid4()), user_id, order_id, points_used, available_points - points_used,
                    f"订单{order_no}使用积分抵扣", datetime.now(),
                ))

            conn.commit()
    except OrderCreateError as e:
        return error_response(e.code, e.message)

    return success_response(data={
        "order_id": order_id,
        "order_no": order_no,
        "total_amount": f"{total_amount:.2f}",
        "freight_amount": f"{freight_amount:.2f}",
        "coupon_amount": f"{coupon_amount:.2f}",
        "points_amount": f"{points_amount:.2f}",
        "pay_amount": f"{pay_amount:.2f}",
    })


@router.get("/orders")
async def get_orders(user: dict = Depends(get_current_user), status: str = "all", page: int = 1, page_size: int = 20):
    user_id = user["user_id"]
    offset = (page - 1) * page_size
    normalized_status = status or "all"
    status_map = {
        "pending": "pending",
        "paid": "paid",
        "shipped": "shipped",
        "delivered": "shipped",
        "received": "received",
        "completed": "completed",
        "cancelled": "cancelled",
        "refunded": "refunded",
    }

    with get_db_cursor() as cursor:
        if normalized_status == "all":
            cursor.execute(
                "SELECT id, order_no, status, total_amount, pay_amount, created_at FROM orders WHERE user_id = %s ORDER BY created_at DESC LIMIT %s OFFSET %s",
                (user_id, page_size, offset),
            )
            orders = cursor.fetchall()
            cursor.execute("SELECT COUNT(*) AS total FROM orders WHERE user_id = %s", (user_id,))
        else:
            db_status = status_map.get(normalized_status, "pending")
            cursor.execute(
                "SELECT id, order_no, status, total_amount, pay_amount, created_at FROM orders WHERE user_id = %s AND status = %s ORDER BY created_at DESC LIMIT %s OFFSET %s",
                (user_id, db_status, page_size, offset),
            )
            orders = cursor.fetchall()
            cursor.execute("SELECT COUNT(*) AS total FROM orders WHERE user_id = %s AND status = %s", (user_id, db_status))
        total = cursor.fetchone()["total"]

        order_ids = [str(order["id"]) for order in orders]
        items_by_order = {}
        if order_ids:
            cursor.execute("""
                SELECT order_id, product_name, product_image, price, quantity, subtotal
                FROM order_items
                WHERE order_id = ANY(%s::uuid[])
                ORDER BY id
            """, (order_ids,))
            for item in cursor.fetchall():
                oid = str(item["order_id"])
                items_by_order.setdefault(oid, []).append({
                    "product_name": item["product_name"],
                    "product_image": item["product_image"],
                    "price": str(item["price"]),
                    "quantity": item["quantity"],
                    "subtotal": str(item["subtotal"]),
                })

    items = []
    for order in orders:
        oid = str(order["id"])
        order_items = items_by_order.get(oid, [])
        items.append({
            "id": oid,
            "order_no": order["order_no"],
            "status": order["status"],
            "total_amount": str(order["total_amount"]),
            "pay_amount": str(order["pay_amount"]),
            "total_count": sum(item["quantity"] for item in order_items),
            "items": order_items,
            "created_at": order["created_at"].isoformat() if order["created_at"] else None,
        })
    return success_response(data=page_response(items, total, page, page_size))


@router.get("/orders/{order_id}")
async def get_order_detail(order_id: str, user: dict = Depends(get_current_user)):
    user_id = user["user_id"]
    with get_db_cursor() as cursor:
        cursor.execute("""
            SELECT id, order_no, address_id, receiver_name, receiver_phone, shipping_address, status,
                   total_amount, freight_amount, coupon_amount, points_amount, pay_amount, points_earned,
                   points_used, delivery_type, delivery_no, delivery_company, pay_time, deliver_time,
                   receive_time, buyer_note, created_at
            FROM orders
            WHERE id = %s AND user_id = %s
        """, (order_id, user_id))
        order = cursor.fetchone()
    if not order:
        return error_response(2003, "订单不存在")

    address = None
    if order.get("receiver_name") or order.get("shipping_address"):
        phone = order["receiver_phone"] or ""
        if phone and len(phone) >= 7:
            phone = phone[:3] + "****" + phone[-4:]
        address = {"receiver_name": order["receiver_name"] or "", "phone": phone, "full_address": order["shipping_address"] or ""}
    elif order.get("address_id"):
        with get_db_cursor() as cursor:
            cursor.execute("SELECT receiver_name, phone, province, city, district, detail_address FROM addresses WHERE id = %s", (str(order["address_id"]),))
            addr = cursor.fetchone()
        if addr:
            phone = addr["phone"]
            if phone and len(phone) >= 7:
                phone = phone[:3] + "****" + phone[-4:]
            address = {"receiver_name": addr["receiver_name"], "phone": phone, "full_address": f"{addr['province']}{addr['city']}{addr['district']}{addr['detail_address']}"}

    with get_db_cursor() as cursor:
        cursor.execute("SELECT product_name, product_image, sku_spec, price, quantity, subtotal FROM order_items WHERE order_id = %s", (order_id,))
        order_items = cursor.fetchall()
    items = [{
        "product_name": item["product_name"],
        "product_image": item["product_image"],
        "sku_spec": item["sku_spec"] or {},
        "price": str(item["price"]),
        "quantity": item["quantity"],
        "subtotal": str(item["subtotal"]),
    } for item in order_items]

    return success_response(data={
        "id": str(order["id"]),
        "order_no": order["order_no"],
        "status": order["status"],
        "address": address,
        "delivery_type": order["delivery_type"],
        "delivery_no": order["delivery_no"] or "",
        "delivery_company": order["delivery_company"] or "",
        "items": items,
        "total_amount": str(order["total_amount"]),
        "freight_amount": str(order["freight_amount"]),
        "coupon_amount": str(order["coupon_amount"]),
        "points_amount": str(order["points_amount"]),
        "pay_amount": str(order["pay_amount"]),
        "points_earned": order["points_earned"],
        "points_used": order["points_used"],
        "pay_time": order["pay_time"].isoformat() if order["pay_time"] else None,
        "deliver_time": order["deliver_time"].isoformat() if order["deliver_time"] else None,
        "receive_time": order["receive_time"].isoformat() if order["receive_time"] else None,
        "created_at": order["created_at"].isoformat() if order["created_at"] else None,
    })


@router.post("/orders/{order_id}/pay")
async def initiate_payment(order_id: str, user: dict = Depends(get_current_user)):
    user_id = user["user_id"]
    with get_db_cursor() as cursor:
        cursor.execute("""
            SELECT o.id, o.order_no, o.pay_amount, o.status, u.openid
            FROM orders o
            JOIN users u ON u.id = o.user_id
            WHERE o.id = %s AND o.user_id = %s
        """, (order_id, user_id))
        order = cursor.fetchone()
    if not order:
        return error_response(2003, "订单不存在")
    if order["status"] != "pending":
        return error_response(1000, "订单状态不允许支付")

    if amount_to_fen(order["pay_amount"]) <= 0:
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE orders SET status = 'paid', pay_time = %s, updated_at = NOW() WHERE id = %s AND status = 'pending'",
                (datetime.now(), order_id),
            )
            conn.commit()
        return success_response(data={"paid": True})

    try:
        params = await jsapi_prepay(
            order_no=order["order_no"],
            amount=order["pay_amount"],
            openid=order["openid"],
            description=f"Liangmu order {order['order_no']}",
        )
    except WechatPayError as exc:
        return error_response(3001, str(exc))
    return success_response(data=params)


@router.put("/orders/{order_id}/cancel")
async def cancel_order(order_id: str, user: dict = Depends(get_current_user)):
    user_id = user["user_id"]
    with get_db_cursor() as cursor:
        cursor.execute("SELECT id, status, points_used FROM orders WHERE id = %s AND user_id = %s", (order_id, user_id))
        order = cursor.fetchone()
    if not order:
        return error_response(2003, "订单不存在")
    if order["status"] != "pending":
        return error_response(1000, "订单状态不允许取消")

    with get_db() as conn:
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        cursor.execute("UPDATE orders SET status = 'cancelled', updated_at = NOW() WHERE id = %s", (order_id,))
        cursor.execute("UPDATE products p SET stock = stock + oi.quantity FROM order_items oi WHERE oi.order_id = %s AND p.id = oi.product_id", (order_id,))
        if order["points_used"] > 0:
            cursor.execute("UPDATE users SET available_points = available_points + %s WHERE id = %s RETURNING available_points", (order["points_used"], user_id))
            balance = cursor.fetchone()["available_points"]
            cursor.execute("""
                INSERT INTO points_log (id, user_id, order_id, type, points, balance, note, created_at)
                VALUES (%s, %s, %s, 'refund', %s, %s, %s, %s)
            """, (str(uuid.uuid4()), user_id, order_id, order["points_used"], balance, "订单取消返还积分", datetime.now()))
        conn.commit()
    return success_response(message="取消成功")


@router.post("/orders/{order_id}/receive")
async def confirm_receive(order_id: str, user: dict = Depends(get_current_user)):
    user_id = user["user_id"]
    with get_db_cursor() as cursor:
        cursor.execute("SELECT id, status FROM orders WHERE id = %s AND user_id = %s", (order_id, user_id))
        order = cursor.fetchone()
    if not order:
        return error_response(2003, "订单不存在")
    if order["status"] not in ("shipped", "delivered"):
        return error_response(1000, "订单状态不允许确认收货")
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE orders SET status = 'received', receive_time = %s, updated_at = NOW() WHERE id = %s", (datetime.now(), order_id))
        conn.commit()
    return success_response(message="确认收货成功")


@router.post("/orders/{order_id}/comment")
async def comment_order(order_id: str, req: Request, user: dict = Depends(get_current_user)):
    user_id = user["user_id"]
    body = await req.json()
    rating = body.get("rating", 5)
    content = body.get("content", "")
    try:
        rating = int(rating)
    except (TypeError, ValueError):
        return error_response(1000, "评分必须是1-5")
    if not (1 <= rating <= 5):
        return error_response(1000, "评分必须是1-5")

    with get_db_cursor() as cursor:
        cursor.execute("SELECT id, status FROM orders WHERE id = %s AND user_id = %s", (order_id, user_id))
        order = cursor.fetchone()
    if not order:
        return error_response(2003, "订单不存在")
    if order["status"] != "received":
        return error_response(1000, "订单状态不允许评价")

    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE orders SET status = 'completed', updated_at = NOW() WHERE id = %s", (order_id,))
        cursor.execute(
            "UPDATE products p SET rating = (SELECT COALESCE(AVG(%s), p.rating) FROM order_items oi WHERE oi.product_id = p.id) WHERE p.id IN (SELECT product_id FROM order_items WHERE order_id = %s)",
            (rating, order_id),
        )
        conn.commit()
    return success_response(message="评价成功", data={"content": content})


@router.post("/notify/pay")
async def wechat_pay_notify(req: Request):
    body_bytes = await req.body()
    try:
        await verify_notify_signature(req.headers, body_bytes)
        body = json.loads(body_bytes.decode("utf-8"))
        resource = decrypt_notify_resource(body.get("resource") or {})
    except Exception as exc:
        return JSONResponse(status_code=400, content={"code": "FAIL", "message": str(exc)})

    order_no = resource.get("out_trade_no", "")
    transaction_id = resource.get("transaction_id", "")
    trade_state = resource.get("trade_state", "")
    payer_total = ((resource.get("amount") or {}).get("payer_total")
                   or (resource.get("amount") or {}).get("total"))
    if not order_no or trade_state != "SUCCESS":
        return JSONResponse(status_code=400, content={"code": "FAIL", "message": "Invalid payment state"})

    with get_db() as conn:
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        cursor.execute("SELECT id, pay_amount, status FROM orders WHERE order_no = %s FOR UPDATE", (order_no,))
        order = cursor.fetchone()
        if not order:
            return JSONResponse(status_code=404, content={"code": "FAIL", "message": "Order not found"})
        expected_total = amount_to_fen(order["pay_amount"])
        if payer_total is not None and int(payer_total) != expected_total:
            return JSONResponse(status_code=400, content={"code": "FAIL", "message": "Amount mismatch"})
        if order["status"] == "pending":
            cursor.execute(
                "UPDATE orders SET status = 'paid', pay_time = %s, updated_at = NOW() WHERE order_no = %s AND status = 'pending'",
                (datetime.now(), order_no),
            )
        conn.commit()

    return {"code": "SUCCESS", "message": "成功", "transaction_id": transaction_id}
