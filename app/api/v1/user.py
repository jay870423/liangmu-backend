"""用户模块API"""
from fastapi import APIRouter, Depends, Request
from app.api.deps import get_current_user, create_access_token
from app.utils.response import success_response, error_response, page_response
from app.database import get_db_cursor, get_db
import httpx
import uuid
import time
from datetime import datetime

router = APIRouter()
_wechat_access_token = {"value": "", "expires_at": 0}


async def get_wechat_access_token():
    from app.config import settings
    if not settings.wechat_appid or not settings.wechat_secret:
        return None, "微信登录配置未完成"
    now = int(time.time())
    if _wechat_access_token["value"] and _wechat_access_token["expires_at"] > now + 60:
        return _wechat_access_token["value"], ""
    token_url = (
        "https://api.weixin.qq.com/cgi-bin/token"
        f"?grant_type=client_credential&appid={settings.wechat_appid}&secret={settings.wechat_secret}"
    )
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(token_url)
            data = resp.json()
    except Exception:
        return None, "微信服务调用失败"
    token = data.get("access_token")
    if not token:
        return None, data.get("errmsg") or "微信 access_token 获取失败"
    _wechat_access_token["value"] = token
    _wechat_access_token["expires_at"] = now + int(data.get("expires_in", 7200))
    return token, ""


def mask_phone(phone: str) -> str:
    if phone and len(phone) >= 7:
        return phone[:3] + "****" + phone[-4:]
    return phone or ""

@router.post("/user/login")
async def wechat_login(req: Request):
    body = await req.json()
    code = body.get("code")
    if not code:
        return error_response(1001, "缺少登录code")
    from app.config import settings
    if not settings.wechat_appid or not settings.wechat_secret:
        return error_response(1000, "微信登录配置未完成")
    wechat_url = f"https://api.weixin.qq.com/sns/jscode2session?appid={settings.wechat_appid}&secret={settings.wechat_secret}&js_code={code}&grant_type=authorization_code"
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(wechat_url)
            wechat_data = resp.json()
    except Exception:
        return error_response(1000, "微信服务调用失败")
    openid = wechat_data.get("openid")
    if not openid:
        return error_response(1000, wechat_data.get("errmsg") or "微信登录失败，无openid")
    with get_db_cursor() as cursor:
        cursor.execute("SELECT * FROM users WHERE openid = %s", (openid,))
        user = cursor.fetchone()
    if user:
        user_id = str(user["id"])
    else:
        user_id = str(uuid.uuid4())
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("INSERT INTO users (id, openid, nickname, avatar_url, member_level, total_points, available_points) VALUES (%s, %s, %s, %s, %s, %s, %s)", (user_id, openid, "", "", "normal", 0, 0))
            conn.commit()
    token = create_access_token(user_id, "")
    with get_db_cursor() as cursor:
        cursor.execute("SELECT id, nickname, avatar_url, phone, member_level, available_points FROM users WHERE id = %s", (user_id,))
        user = cursor.fetchone()
    return success_response(data={"token": token, "user_id": str(user["id"]), "nickname": user["nickname"] or "", "avatar_url": user["avatar_url"] or "", "phone": mask_phone(user["phone"] or ""), "member_level": user["member_level"], "available_points": user["available_points"]}, message="登录成功")


@router.post("/user/phone")
async def bind_phone(req: Request, user: dict = Depends(get_current_user)):
    body = await req.json()
    code = body.get("code")
    if not code:
        return error_response(1001, "缺少手机号授权code")
    access_token, err = await get_wechat_access_token()
    if not access_token:
        return error_response(1000, err)
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                f"https://api.weixin.qq.com/wxa/business/getuserphonenumber?access_token={access_token}",
                json={"code": code},
            )
            phone_data = resp.json()
    except Exception:
        return error_response(1000, "微信手机号服务调用失败")
    if phone_data.get("errcode", 0) != 0:
        return error_response(1000, phone_data.get("errmsg") or "手机号授权失败")
    phone_info = phone_data.get("phone_info") or {}
    phone = phone_info.get("purePhoneNumber") or phone_info.get("phoneNumber")
    if not phone:
        return error_response(1000, "未获取到手机号")
    user_id = user["user_id"]
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET phone = %s WHERE id = %s", (phone, user_id))
        conn.commit()
    return success_response(data={"phone": mask_phone(phone)}, message="手机号绑定成功")

@router.get("/user/info")
async def get_user_info(user: dict = Depends(get_current_user)):
    user_id = user["user_id"]
    with get_db_cursor() as cursor:
        cursor.execute("SELECT id, nickname, avatar_url, phone, member_level, total_points, available_points, created_at FROM users WHERE id = %s", (user_id,))
        user_data = cursor.fetchone()
    if not user_data:
        return error_response(1002, "用户不存在")
    phone = mask_phone(user_data["phone"] or "")
    return success_response(data={"user_id": str(user_data["id"]), "nickname": user_data["nickname"] or "", "avatar_url": user_data["avatar_url"] or "", "phone": phone, "member_level": user_data["member_level"], "total_points": user_data["total_points"], "available_points": user_data["available_points"], "created_at": user_data["created_at"].isoformat() if user_data["created_at"] else None})

@router.get("/user/points")
async def get_points(user: dict = Depends(get_current_user)):
    user_id = user["user_id"]
    with get_db_cursor() as cursor:
        cursor.execute("SELECT total_points, available_points FROM users WHERE id = %s", (user_id,))
        user_data = cursor.fetchone()
    total = user_data["total_points"] if user_data else 0
    available = user_data["available_points"] if user_data else 0
    return success_response(data={"total_points": total, "available_points": available, "points_value": round(available / 100, 2)})

@router.get("/user/points/log")
async def get_points_log(user: dict = Depends(get_current_user), page: int = 1, page_size: int = 20):
    user_id = user["user_id"]
    offset = (page - 1) * page_size
    with get_db_cursor() as cursor:
        cursor.execute("SELECT id, type, points, balance, note, created_at FROM points_log WHERE user_id = %s ORDER BY created_at DESC LIMIT %s OFFSET %s", (user_id, page_size, offset))
        items = cursor.fetchall()
        cursor.execute("SELECT COUNT(*) as total FROM points_log WHERE user_id = %s", (user_id,))
        total = cursor.fetchone()["total"]
    result_items = [{"id": str(item["id"]), "type": item["type"], "points": item["points"], "balance": item["balance"], "note": item["note"] or "", "created_at": item["created_at"].isoformat() if item["created_at"] else None} for item in items]
    return success_response(data=page_response(result_items, total, page, page_size))

@router.put("/user/nickname")
async def update_nickname(req: Request, user: dict = Depends(get_current_user)):
    user_id = user["user_id"]
    body = await req.json()
    nickname = body.get("nickname", "")
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET nickname = %s WHERE id = %s", (nickname, user_id))
        conn.commit()
    return success_response(message="昵称更新成功")
