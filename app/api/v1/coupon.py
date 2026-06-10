"""优惠券模块API"""
from fastapi import APIRouter, Depends, Request
from app.api.deps import get_current_user
from app.utils.response import success_response, error_response, page_response
from app.database import get_db_cursor, get_db
from datetime import datetime
import uuid

router = APIRouter()

@router.get("/coupons")
async def get_available_coupons(user: dict = Depends(get_current_user)):
    user_id = user["user_id"]
    now = datetime.now()
    with get_db_cursor() as cursor:
        cursor.execute("SELECT c.id, c.name, c.type, c.discount_amount, c.min_order_amount, c.total_count, c.remain_count, c.start_time, c.end_time FROM coupons c WHERE c.is_active = true AND c.remain_count > 0 AND c.end_time > %s ORDER BY c.end_time ASC", (now,))
        coupons = cursor.fetchall()
        cursor.execute("SELECT coupon_id FROM user_coupons WHERE user_id = %s", (user_id,))
        my_coupon_ids = {str(row["coupon_id"]) for row in cursor.fetchall()}
    items = []
    for c in coupons:
        cid = str(c["id"])
        items.append({"id": cid, "name": c["name"], "type": c["type"], "discount_amount": str(c["discount_amount"]), "min_order_amount": str(c["min_order_amount"]), "total_count": c["total_count"], "remain_count": c["remain_count"], "start_time": c["start_time"].isoformat() if c["start_time"] else None, "end_time": c["end_time"].isoformat() if c["end_time"] else None, "has_received": cid in my_coupon_ids})
    return success_response(data={"items": items})

@router.get("/user/coupons")
async def get_my_coupons(user: dict = Depends(get_current_user), status: str = "unused"):
    user_id = user["user_id"]
    now = datetime.now()
    with get_db_cursor() as cursor:
        if status == "used":
            cursor.execute("SELECT uc.id, uc.coupon_id, uc.status, uc.used_at, uc.created_at, c.name, c.type, c.discount_amount, c.min_order_amount, c.end_time FROM user_coupons uc JOIN coupons c ON uc.coupon_id = c.id WHERE uc.user_id = %s AND uc.status = 'used' ORDER BY uc.used_at DESC", (user_id,))
        elif status == "expired":
            cursor.execute("SELECT uc.id, uc.coupon_id, uc.status, uc.used_at, uc.created_at, c.name, c.type, c.discount_amount, c.min_order_amount, c.end_time FROM user_coupons uc JOIN coupons c ON uc.coupon_id = c.id WHERE uc.user_id = %s AND uc.status = 'unused' AND c.end_time < %s ORDER BY c.end_time DESC", (user_id, now))
        else:
            cursor.execute("SELECT uc.id, uc.coupon_id, uc.status, uc.used_at, uc.created_at, c.name, c.type, c.discount_amount, c.min_order_amount, c.end_time FROM user_coupons uc JOIN coupons c ON uc.coupon_id = c.id WHERE uc.user_id = %s AND uc.status = 'unused' AND c.end_time >= %s ORDER BY c.end_time ASC", (user_id, now))
        coupons = cursor.fetchall()
    items = []
    for c in coupons:
        items.append({"id": str(c["id"]), "user_coupon_id": str(c["id"]), "coupon_id": str(c["coupon_id"]), "name": c["name"], "type": c["type"], "discount_amount": str(c["discount_amount"]), "min_order_amount": str(c["min_order_amount"]), "status": c["status"], "end_time": c["end_time"].isoformat() if c["end_time"] else None, "used_at": c["used_at"].isoformat() if c["used_at"] else None, "created_at": c["created_at"].isoformat() if c["created_at"] else None})
    return success_response(data={"items": items})

@router.post("/user/coupons/{coupon_id}/receive")
async def receive_coupon(coupon_id: str, user: dict = Depends(get_current_user)):
    user_id = user["user_id"]
    now = datetime.now()
    with get_db_cursor() as cursor:
        cursor.execute("SELECT id, remain_count, total_count, end_time, is_active FROM coupons WHERE id = %s", (coupon_id,))
        coupon = cursor.fetchone()
    if not coupon:
        return error_response(1000, "优惠券不存在")
    if coupon["remain_count"] <= 0:
        return error_response(2004, "优惠券已领完")
    if coupon["end_time"] < now:
        return error_response(2004, "优惠券已过期")
    with get_db_cursor() as cursor:
        cursor.execute("SELECT id FROM user_coupons WHERE user_id = %s AND coupon_id = %s AND status = 'unused'", (user_id, coupon_id))
        if cursor.fetchone():
            return error_response(1000, "已领取过该优惠券")
    user_coupon_id = str(uuid.uuid4())
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("INSERT INTO user_coupons (id, user_id, coupon_id, status) VALUES (%s, %s, %s, 'unused')", (user_coupon_id, user_id, coupon_id))
        cursor.execute("UPDATE coupons SET remain_count = remain_count - 1 WHERE id = %s", (coupon_id,))
        conn.commit()
    return success_response(data={"user_coupon_id": user_coupon_id}, message="领取成功")
