"""收货地址模块API"""
from fastapi import APIRouter, Depends, Request
from app.api.deps import get_current_user
from app.utils.response import success_response, error_response
from app.database import get_db_cursor, get_db
import uuid

router = APIRouter()

@router.get("/addresses")
async def get_addresses(user: dict = Depends(get_current_user)):
    user_id = user["user_id"]
    with get_db_cursor() as cursor:
        cursor.execute("SELECT id, receiver_name, phone, province, city, district, detail_address, is_default FROM addresses WHERE user_id = %s ORDER BY is_default DESC, created_at DESC", (user_id,))
        addresses = cursor.fetchall()
    items = [{"id": str(a["id"]), "receiver_name": a["receiver_name"], "phone": a["phone"], "province": a["province"], "city": a["city"], "district": a["district"], "detail_address": a["detail_address"], "is_default": a["is_default"]} for a in addresses]
    return success_response(data={"items": items})

@router.post("/addresses")
async def create_address(req: Request, user: dict = Depends(get_current_user)):
    user_id = user["user_id"]
    body = await req.json()
    receiver_name = body.get("receiver_name", "").strip()
    phone = body.get("phone", "").strip()
    province = body.get("province", "").strip()
    city = body.get("city", "").strip()
    district = body.get("district", "").strip()
    detail_address = body.get("detail_address", "").strip()
    is_default = body.get("is_default", False)
    if not all([receiver_name, phone, province, city, district, detail_address]):
        return error_response(1001, "缺少必填字段")
    if is_default:
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("UPDATE addresses SET is_default = false WHERE user_id = %s", (user_id,))
            conn.commit()
    address_id = str(uuid.uuid4())
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("INSERT INTO addresses (id, user_id, receiver_name, phone, province, city, district, detail_address, is_default) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)", (address_id, user_id, receiver_name, phone, province, city, district, detail_address, is_default))
        conn.commit()
    return success_response(data={"address_id": address_id}, message="添加成功")

@router.put("/addresses/{address_id}")
async def update_address(address_id: str, req: Request, user: dict = Depends(get_current_user)):
    user_id = user["user_id"]
    body = await req.json()
    with get_db_cursor() as cursor:
        cursor.execute("SELECT id FROM addresses WHERE id = %s AND user_id = %s", (address_id, user_id))
        if not cursor.fetchone():
            return error_response(1000, "地址不存在")
    receiver_name = body.get("receiver_name", "").strip()
    phone = body.get("phone", "").strip()
    province = body.get("province", "").strip()
    city = body.get("city", "").strip()
    district = body.get("district", "").strip()
    detail_address = body.get("detail_address", "").strip()
    is_default = body.get("is_default", False)
    if is_default:
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("UPDATE addresses SET is_default = false WHERE user_id = %s", (user_id,))
            conn.commit()
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE addresses SET receiver_name=%s, phone=%s, province=%s, city=%s, district=%s, detail_address=%s, is_default=%s WHERE id = %s AND user_id = %s", (receiver_name, phone, province, city, district, detail_address, is_default, address_id, user_id))
        conn.commit()
    return success_response(message="更新成功")

@router.delete("/addresses/{address_id}")
async def delete_address(address_id: str, user: dict = Depends(get_current_user)):
    user_id = user["user_id"]
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM addresses WHERE id = %s AND user_id = %s", (address_id, user_id))
        conn.commit()
    return success_response(message="删除成功")

@router.put("/addresses/{address_id}/default")
async def set_default_address(address_id: str, user: dict = Depends(get_current_user)):
    user_id = user["user_id"]
    with get_db_cursor() as cursor:
        cursor.execute("SELECT id FROM addresses WHERE id = %s AND user_id = %s", (address_id, user_id))
        if not cursor.fetchone():
            return error_response(1000, "地址不存在")
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE addresses SET is_default = false WHERE user_id = %s", (user_id,))
        cursor.execute("UPDATE addresses SET is_default = true WHERE id = %s AND user_id = %s", (address_id, user_id))
        conn.commit()
    return success_response(message="设置成功")
