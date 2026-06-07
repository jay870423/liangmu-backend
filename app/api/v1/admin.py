from fastapi import Query, APIRouter, HTTPException, UploadFile, File
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from datetime import date, datetime
import json, secrets, httpx, os, uuid, aiofiles
from app.database import get_db_cursor

ASSET_UPLOAD_DIR = "/home/ubuntu/liangmu-admin/assets/uploads"
ASSET_UPLOAD_PREFIX = "/assets/uploads"
os.makedirs(ASSET_UPLOAD_DIR, exist_ok=True)

def _ext_from_content_type(content_type: str, default: str = ".jpg") -> str:
    content_type = (content_type or "").lower()
    if "png" in content_type:
        return ".png"
    if "webp" in content_type:
        return ".webp"
    if "svg" in content_type:
        return ".svg"
    if "jpeg" in content_type or "jpg" in content_type:
        return ".jpg"
    return default

def _save_generated_image(image_url: str, prefix: str) -> str:
    resp = httpx.get(image_url, timeout=60.0, follow_redirects=True)
    resp.raise_for_status()
    ext = _ext_from_content_type(resp.headers.get("content-type"), ".jpg")
    filename = f"{prefix}_{uuid.uuid4().hex}{ext}"
    filepath = os.path.join(ASSET_UPLOAD_DIR, filename)
    with open(filepath, "wb") as f:
        f.write(resp.content)
    return f"{ASSET_UPLOAD_PREFIX}/{filename}"


router = APIRouter(prefix="/admin", tags=["admin"])

class LoginReq(BaseModel):
    username: str
    password: str

@router.post("/login")
async def admin_login(req: LoginReq):
    if req.username != "admin" or req.password != "yl888888":
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    token = secrets.token_hex(32)
    return {"token": token, "username": "admin"}

@router.get("/stats")
async def get_stats():
    try:
        with get_db_cursor() as cur:
            today = date.today().isoformat()
            cur.execute("SELECT COUNT(*) FROM orders WHERE DATE(created_at) = %s", (today,))
            today_orders = cur.fetchone()["count"]
            cur.execute("SELECT COALESCE(SUM(total_amount), 0) FROM orders WHERE DATE(created_at) = %s AND status != 'refunded'", (today,))
            today_sales = float(cur.fetchone()["coalesce"] or 0)
            cur.execute("SELECT COUNT(*) FROM users WHERE DATE(created_at) = %s", (today,))
            today_users = cur.fetchone()["count"]
            cur.execute("SELECT COUNT(*) FROM products")
            total_products = cur.fetchone()["count"]
            cur.execute("SELECT COUNT(*) FROM orders WHERE status = 'pending'")
            pending_payment_orders = cur.fetchone()["count"]
            cur.execute("SELECT COUNT(*) FROM orders WHERE status = 'paid'")
            paid_orders = cur.fetchone()["count"]
            cur.execute("SELECT id, name, stock FROM products WHERE stock < 10 ORDER BY stock ASC LIMIT 5")
            low_stock = [{"id": str(r["id"]), "name": r["name"], "stock": r["stock"]} for r in cur.fetchall()]
            return {
                "today_orders": today_orders, "today_sales": today_sales, "today_users": today_users,
                "total_products": total_products,
                "pending_orders": paid_orders,
                "paid_orders": paid_orders,
                "pending_payment_orders": pending_payment_orders,
                "low_stock_products": low_stock
            }
    except Exception:
        return {
            "today_orders": 0, "today_sales": 0, "today_users": 0,
            "total_products": 0, "pending_orders": 0, "paid_orders": 0,
            "pending_payment_orders": 0, "low_stock_products": []
        }

# ===== 订单管理 =====
@router.get("/orders")
async def list_orders(page: int = 1, page_size: int = 10, status: str = None, keyword: str = None):
    offset = (page - 1) * page_size
    try:
        with get_db_cursor() as cur:
            conditions = []
            query_params = []
            if status and status != 'all':
                conditions.append("o.status = %s")
                query_params.append(status)
            if keyword and keyword.strip():
                like = f"%{keyword.strip()}%"
                conditions.append("""(
                    o.order_no ILIKE %s OR
                    COALESCE(o.receiver_name, '') ILIKE %s OR
                    COALESCE(o.receiver_phone, '') ILIKE %s OR
                    COALESCE(o.shipping_address, '') ILIKE %s OR
                    COALESCE(a.receiver_name, '') ILIKE %s OR
                    COALESCE(a.phone, '') ILIKE %s OR
                    TRIM(CONCAT_WS('', a.province, a.city, a.district, a.detail_address)) ILIKE %s OR
                    EXISTS (
                        SELECT 1 FROM order_items oi2
                        WHERE oi2.order_id = o.id AND COALESCE(oi2.product_name, '') ILIKE %s
                    )
                )""")
                query_params.extend([like] * 8)
            where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
            cur.execute(f"""
                SELECT COUNT(*) FROM orders o
                LEFT JOIN addresses a ON o.address_id = a.id
                LEFT JOIN users u ON o.user_id = u.id
                {where}
            """, query_params)
            total = cur.fetchone()["count"]
            params = query_params + [page_size, offset]
            cur.execute(f"""
                SELECT o.id, o.order_no, o.user_id, o.status, o.total_amount, o.pay_amount, o.buyer_note,
                       o.created_at, o.delivery_company, o.delivery_no,
                       COALESCE(u.nickname, '') AS user_nickname,
                       COALESCE(u.phone, '') AS user_phone,
                       COALESCE(u.member_level, '') AS user_member_level,
                       COALESCE(u.openid, '') AS user_openid,
                       COALESCE(NULLIF(o.receiver_name, ''), a.receiver_name, '') AS receiver_name,
                       COALESCE(NULLIF(o.receiver_phone, ''), a.phone, '') AS receiver_phone,
                       COALESCE(NULLIF(o.shipping_address, ''), TRIM(CONCAT_WS('', a.province, a.city, a.district, a.detail_address)), '') AS shipping_address,
                       COALESCE(json_agg(
                           json_build_object(
                               'name', oi.product_name,
                               'quantity', oi.quantity,
                               'price', oi.price,
                               'image', oi.product_image
                           )
                       ) FILTER (WHERE oi.id IS NOT NULL), '[]') AS items
                FROM orders o
                LEFT JOIN addresses a ON o.address_id = a.id
                LEFT JOIN users u ON o.user_id = u.id
                LEFT JOIN order_items oi ON o.id = oi.order_id
                {where}
                GROUP BY o.id, u.nickname, u.phone, u.member_level, u.openid, a.receiver_name, a.phone, a.province, a.city, a.district, a.detail_address
                ORDER BY o.created_at DESC LIMIT %s OFFSET %s
            """, params)
            rows = cur.fetchall()
            orders = [{
                "id": str(r["id"]),
                "order_no": r["order_no"] or str(r["id"]),
                "user_id": str(r["user_id"]) if r["user_id"] else "",
                "user_nickname": r["user_nickname"] or "",
                "user_phone": r["user_phone"] or "",
                "user_member_level": r["user_member_level"] or "",
                "user_openid": r["user_openid"] or "",
                "status": r["status"],
                "total_amount": float(r["total_amount"] or 0),
                "pay_amount": float(r["pay_amount"] or 0),
                "receiver_name": r["receiver_name"] or "",
                "receiver_phone": r["receiver_phone"] or "",
                "shipping_address": r["shipping_address"] or "",
                "buyer_note": r["buyer_note"] or "",
                "delivery_company": r["delivery_company"] or "",
                "delivery_no": r["delivery_no"] or "",
                "items": r["items"] or [],
                "created_at": r["created_at"].isoformat() if r["created_at"] else ""
            } for r in rows]
            return {"items": orders, "total": total}
    except Exception as e:
        return {"items": [], "total": 0, "error": str(e)}

@router.put("/orders/{order_id}/status")
async def update_order_status(order_id: str, status: str):
    """更新订单状态：shipped（发货）/refunded（退款）/cancelled（取消）"""
    allowed = {"shipped": "shipped", "refunded": "refunded", "cancelled": "cancelled"}
    if status not in allowed:
        raise HTTPException(status_code=400, detail="无效状态")
    try:
        with get_db_cursor() as cur:
            cur.execute("SELECT id, status FROM orders WHERE id = %s FOR UPDATE", (order_id,))
            order = cur.fetchone()
            if not order:
                raise HTTPException(status_code=404, detail="订单不存在")
            old_status = order["status"]
            new_status = allowed[status]
            cur.execute("UPDATE orders SET status = %s, updated_at = NOW() WHERE id = %s", (new_status, order_id))
            if new_status in ("cancelled", "refunded") and old_status not in ("cancelled", "refunded"):
                cur.execute("""
                    UPDATE products p
                    SET stock = stock + oi.quantity,
                        sales_count = GREATEST(0, sales_count - oi.quantity),
                        updated_at = NOW()
                    FROM order_items oi
                    WHERE oi.order_id = %s AND p.id = oi.product_id
                """, (order_id,))
        return {"success": True, "message": "更新成功"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ===== 用户管理 =====
@router.get("/users")
async def list_users(page: int = 1, page_size: int = 10, keyword: str = None):
    offset = (page - 1) * page_size
    try:
        with get_db_cursor() as cur:
            where = "WHERE u.nickname ILIKE %s OR u.phone ILIKE %s" if keyword else ""
            count_params = [f"%{keyword}%", f"%{keyword}%"] if keyword else []
            cur.execute(f"SELECT COUNT(*) FROM users u {where}", count_params)
            total = cur.fetchone()["count"]
            params = count_params + [page_size, offset]
            cur.execute(f"""
                SELECT u.id, u.nickname, u.phone, u.member_level, u.total_points, u.available_points, u.created_at,
                       COALESCE(SUM(o.total_amount) FILTER (WHERE o.status NOT IN ('cancelled','refunded')), 0) AS total_spent,
                       COUNT(o.id) AS order_count
                FROM users u
                LEFT JOIN orders o ON o.user_id = u.id
                {where}
                GROUP BY u.id
                ORDER BY u.created_at DESC LIMIT %s OFFSET %s
            """, params)
            rows = cur.fetchall()
            users = [{
                "id": str(r["id"]),
                "nickname": r["nickname"] or f"用户{str(r['id'])[:8]}",
                "phone": r["phone"] or "",
                "member_level": r["member_level"] or "normal",
                "total_points": r["total_points"] or 0,
                "available_points": r["available_points"] or 0,
                "points": r["available_points"] or 0,
                "total_spent": float(r["total_spent"] or 0),
                "order_count": r["order_count"] or 0,
                "created_at": r["created_at"].isoformat() if r["created_at"] else ""
            } for r in rows]
            return {"items": users, "total": total}
    except Exception as e:
        return {"items": [], "total": 0, "error": str(e)}

@router.get("/users/{user_id}/points")
async def get_user_points(user_id: str):
    try:
        with get_db_cursor() as cur:
            cur.execute("SELECT available_points FROM users WHERE id = %s", (user_id,))
            r = cur.fetchone()
            if not r:
                raise HTTPException(status_code=404, detail="用户不存在")
            return {"points": r["available_points"] or 0}
    except HTTPException:
        raise
    except Exception:
        return {"points": 0}

@router.put("/users/{user_id}/points")
async def adjust_user_points(user_id: str, points_delta: int = Query(..., description="积分变化量，正数增加，负数减少")):
    """调整用户积分"""
    try:
        with get_db_cursor() as cur:
            cur.execute("UPDATE users SET available_points = GREATEST(0, available_points + %s), total_points = GREATEST(0, total_points + GREATEST(%s, 0)) WHERE id = %s", (points_delta, points_delta, user_id))
            if cur.rowcount == 0:
                raise HTTPException(status_code=404, detail="用户不存在")
            cur.execute("SELECT available_points FROM users WHERE id = %s", (user_id,))
            new_points = cur.fetchone()["available_points"]
        return {"success": True, "points": new_points}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ===== AI 能力 =====
def _call_minimax(prompt: str, timeout: float = 30.0) -> str:
    import os
    api_key = os.getenv("MINIMAX_API_KEY", "")
    if not api_key:
        return "AI功能暂未配置API Key"
    try:
        resp = httpx.post(
            "https://api.minimaxi.com/v1/text/chatcompletion_v2",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={"model": "MiniMax-M2.7-highspeed", "messages": [{"role": "user", "content": prompt}]},
            timeout=timeout
        )
        return resp.json().get("choices", [{}])[0].get("message", {}).get("content", "处理完毕")
    except Exception as e:
        return f"服务暂时不可用：{str(e)}"

def _extract_stream_piece(payload):
    choices = payload.get("choices") if isinstance(payload, dict) else None
    if isinstance(choices, list):
        for choice in choices:
            if not isinstance(choice, dict):
                continue
            delta = choice.get("delta") or {}
            if isinstance(delta, dict):
                content = delta.get("content")
                if isinstance(content, str) and content:
                    return content, False
            message = choice.get("message") or {}
            if isinstance(message, dict):
                content = message.get("content")
                if isinstance(content, str) and content:
                    return content, True
    if isinstance(payload, dict):
        content = payload.get("content") or payload.get("text")
        if isinstance(content, str) and content:
            return content, False
    return "", False

async def _stream_minimax_messages(messages):
    api_key = os.getenv("MINIMAX_API_KEY", "")
    if not api_key:
        yield "AI API Key is not configured."
        return
    emitted_text = ""
    emitted = False
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(90.0, read=180.0)) as client:
            async with client.stream(
                "POST",
                "https://api.minimaxi.com/v1/text/chatcompletion_v2",
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json={"model": "MiniMax-M2.7-highspeed", "messages": messages, "stream": True},
            ) as resp:
                if resp.status_code >= 400:
                    detail = (await resp.aread()).decode("utf-8", errors="ignore")[:300]
                    yield f"AI service unavailable: {detail or resp.status_code}"
                    return
                async for line in resp.aiter_lines():
                    line = (line or "").strip()
                    if not line:
                        continue
                    if line.startswith("data:"):
                        line = line[5:].strip()
                    if line == "[DONE]":
                        break
                    try:
                        payload = json.loads(line)
                    except Exception:
                        continue
                    piece, is_full = _extract_stream_piece(payload)
                    if not piece:
                        continue
                    if is_full:
                        if piece == emitted_text or piece.strip() == emitted_text.strip() or piece in emitted_text:
                            chunk = ""
                        elif piece.startswith(emitted_text):
                            chunk = piece[len(emitted_text):]
                            emitted_text = piece
                        elif emitted_text and emitted_text.strip() and emitted_text.strip() in piece:
                            idx = piece.find(emitted_text.strip())
                            chunk = piece[idx + len(emitted_text.strip()):]
                            emitted_text += chunk
                        else:
                            chunk = piece
                            emitted_text += chunk
                    else:
                        chunk = piece
                        emitted_text += chunk
                    if chunk:
                        emitted = True
                        yield chunk
        if not emitted:
            yield "Done"
    except Exception as e:
        yield f"AI service unavailable: {str(e)}"

def _stream_response(messages):
    return StreamingResponse(
        _stream_minimax_messages(messages),
        media_type="text/plain; charset=utf-8",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )

@router.get("/ai/analyze")
async def ai_analyze(type: str = Query(...), data: str = Query("{}")):
    prompt = f"作为电商运营专家，分析以下数据并给出建议：\n{data}"
    return {"analysis": _call_minimax(prompt)}

@router.get("/ai/analyze/stream")
async def ai_analyze_stream(type: str = Query(...), data: str = Query("{}")):
    prompt = f"Please answer in Chinese. As an ecommerce operations expert, analyze this dashboard data and give practical suggestions:\n{data}"
    return _stream_response([{"role": "user", "content": prompt}])

@router.get("/ai/generate_desc")
async def generate_product_desc(product_name: str, category: str):
    prompt = f"为'{product_name}'（分类：{category}）写一段50-100字的商品描述，突出材质、工艺、收藏价值。语气高端典雅。"
    return {"description": _call_minimax(prompt)}

@router.get("/ai/generate_desc/stream")
async def generate_product_desc_stream(product_name: str, category: str):
    prompt = f"Please answer in Chinese. Write a 50-100 Chinese character premium product description for product '{product_name}' in category '{category}'. Highlight material, craft, and collection value."
    return _stream_response([{"role": "user", "content": prompt}])

class AICallReq(BaseModel):
    message: str
    context: str = None

@router.post("/ai/chat")
async def ai_chat(req: AICallReq):
    system_prompt = "你是小吉微商城的AI运营助手，职责：分析销售数据、回答商品订单用户问题、提供营销建议、生成文案活动方案。请用专业但易懂的语言回答。"
    messages = [{"role": "system", "content": system_prompt}]
    if req.context:
        messages.append({"role": "user", "content": req.context})
    messages.append({"role": "user", "content": req.message})
    try:
        import os
        api_key = os.getenv("MINIMAX_API_KEY", "")
        if not api_key:
            return {"message": "AI助手暂未配置API Key，请联系管理员。"}
        resp = httpx.post(
            "https://api.minimaxi.com/v1/text/chatcompletion_v2",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={"model": "MiniMax-M2.7-highspeed", "messages": messages},
            timeout=60.0
        )
        content = resp.json().get("choices", [{}])[0].get("message", {}).get("content", "处理完毕")
        return {"message": content}
    except Exception as e:
        return {"message": f"服务暂时不可用：{str(e)}"}

@router.post("/ai/chat/stream")
async def ai_chat_stream(req: AICallReq):
    system_prompt = "You are the AI operations assistant for Xiaoji micro mall. Reply in Chinese. Help analyze sales data, answer order and product questions, generate marketing copy, and provide practical operations suggestions."
    messages = [{"role": "system", "content": system_prompt}]
    if req.context:
        messages.append({"role": "user", "content": req.context})
    messages.append({"role": "user", "content": req.message})
    return _stream_response(messages)

@router.post("/ai/predict")
async def ai_predict(type: str, data: dict):
    prompt = f"作为电商数据分析师，基于以下历史数据预测{type}趋势，给出预测结论和具体建议：\n{json.dumps(data, ensure_ascii=False)}"
    return {"prediction": _call_minimax(prompt)}

@router.post("/ai/predict/stream")
async def ai_predict_stream(type: str, data: dict):
    prompt = f"Please answer in Chinese. As an ecommerce data analyst, predict the {type} trend from this history and provide conclusions plus concrete suggestions:\n{json.dumps(data, ensure_ascii=False)}"
    return _stream_response([{"role": "user", "content": prompt}])

# ===== 图片生成 & 上传 =====
@router.get("/ai/generate_image")
async def generate_product_image(product_name: str, category: str = ""):
    """用 MiniMax 图片生成模型为商品生成图片"""
    import os
    api_key = os.getenv("MINIMAX_API_KEY", "")
    if not api_key:
        return {"image_url": "", "error": "API Key未配置"}
    try:
        prompt = (
            f"专业商品摄影风格，{category}类目：{product_name}，"
            f"高端木质工艺品展示，纯色背景，光线柔和，8K超清，无文字无水印，"
            f"适合电商主图"
        )
        resp = httpx.post(
            "https://api.minimaxi.com/v1/image_generation",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={
                "model": "image-01",
                "prompt": prompt,
                "response_format": "url"
            },
            timeout=60.0
        )
        result = resp.json()
        image_url = result.get("data", {}).get("image_urls", [""])[0]
        if not image_url:
            return {"image_url": "", "error": "生成失败，请重试"}
        local_url = _save_generated_image(image_url, "product")
        return {"image_url": local_url}
    except Exception as e:
        return {"image_url": "", "error": str(e)}

@router.post("/upload/image")
async def upload_product_image(file: UploadFile = File(...)):
    """Upload product images to /assets/uploads/."""
    ext = os.path.splitext(file.filename)[1] or ".jpg"
    if ext.lower() not in [".jpg", ".jpeg", ".png", ".webp"]:
        raise HTTPException(status_code=400, detail="Only jpg/png/webp files are supported")
    filename = f"product_{uuid.uuid4().hex}{ext.lower()}"
    filepath = os.path.join(ASSET_UPLOAD_DIR, filename)
    content = await file.read()
    if len(content) > 5 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="Image must be 5MB or smaller")
    with open(filepath, "wb") as f:
        f.write(content)
    return {"url": f"{ASSET_UPLOAD_PREFIX}/{filename}"}
