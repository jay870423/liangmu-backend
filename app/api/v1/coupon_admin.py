from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
from datetime import datetime
import uuid

router = APIRouter(prefix="/admin/coupons", tags=["admin-coupon"])

class CouponCreate(BaseModel):
    name: str
    type: str = "discount"  # discount/full_down
    discount_amount: float = 0
    min_order_amount: float = 0
    total_count: int = 100
    start_time: str = ""
    end_time: str = ""
    is_active: bool = True

class CouponUpdate(BaseModel):
    name: Optional[str] = None
    type: Optional[str] = None
    discount_amount: Optional[float] = None
    min_order_amount: Optional[float] = None
    total_count: Optional[int] = None
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    is_active: Optional[bool] = None

@router.get("/")
async def list_coupons(page: int = 1, page_size: int = 10, keyword: str = None):
    from app.database import get_db_cursor
    offset = (page - 1) * page_size
    with get_db_cursor() as cur:
        if keyword:
            cur.execute("SELECT COUNT(*) FROM coupons WHERE name LIKE %s", (f"%{keyword}%",))
        else:
            cur.execute("SELECT COUNT(*) FROM coupons")
        total = cur.fetchone()["count"]
        if keyword:
            cur.execute("""SELECT c.*, (SELECT COUNT(*) FROM user_coupons uc WHERE uc.coupon_id = c.id) as claimed_count
                           FROM coupons c WHERE c.name LIKE %s ORDER BY c.created_at DESC LIMIT %s OFFSET %s""",
                        (f"%{keyword}%", page_size, offset))
        else:
            cur.execute("""SELECT c.*, (SELECT COUNT(*) FROM user_coupons uc WHERE uc.coupon_id = c.id) as claimed_count
                           FROM coupons c ORDER BY c.created_at DESC LIMIT %s OFFSET %s""",
                        (page_size, offset))
        rows = cur.fetchall()
        items = [{
            "id": str(r["id"]), "name": r["name"], "type": r["type"],
            "discount_amount": float(r["discount_amount"]),
            "min_order_amount": float(r["min_order_amount"]),
            "total_count": r["total_count"], "remain_count": r["remain_count"],
            "claimed_count": r["claimed_count"] or 0,
            "start_time": r["start_time"].isoformat() if r["start_time"] else "",
            "end_time": r["end_time"].isoformat() if r["end_time"] else "",
            "is_active": r["is_active"],
            "created_at": r["created_at"].isoformat() if r["created_at"] else ""
        } for r in rows]
        return {"items": items, "total": total}

@router.post("/")
async def create_coupon(req: CouponCreate):
    from app.database import get_db_cursor
    coupon_id = str(uuid.uuid4())
    start = datetime.fromisoformat(req.start_time) if req.start_time else datetime.now()
    end = datetime.fromisoformat(req.end_time) if req.end_time else datetime.now()
    with get_db_cursor() as cur:
        cur.execute("""INSERT INTO coupons (id, name, type, discount_amount, min_order_amount, total_count, remain_count, start_time, end_time, is_active)
                       VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                    (coupon_id, req.name, req.type, req.discount_amount, req.min_order_amount,
                     req.total_count, req.total_count, start, end, req.is_active))
    return {"id": coupon_id, "message": "创建成功"}

@router.put("/{coupon_id}")
async def update_coupon(coupon_id: str, req: CouponUpdate):
    from app.database import get_db_cursor
    with get_db_cursor() as cur:
        cur.execute("SELECT id FROM coupons WHERE id = %s", (coupon_id,))
        if not cur.fetchone():
            raise HTTPException(status_code=404, detail="优惠券不存在")
        updates = []
        vals = []
        if req.name is not None: updates.append("name=%s"); vals.append(req.name)
        if req.type is not None: updates.append("type=%s"); vals.append(req.type)
        if req.discount_amount is not None: updates.append("discount_amount=%s"); vals.append(req.discount_amount)
        if req.min_order_amount is not None: updates.append("min_order_amount=%s"); vals.append(req.min_order_amount)
        if req.total_count is not None: updates.append("total_count=%s"); vals.append(req.total_count)
        if req.start_time is not None: updates.append("start_time=%s"); vals.append(datetime.fromisoformat(req.start_time))
        if req.end_time is not None: updates.append("end_time=%s"); vals.append(datetime.fromisoformat(req.end_time))
        if req.is_active is not None: updates.append("is_active=%s"); vals.append(req.is_active)
        if updates:
            vals.append(coupon_id)
            cur.execute(f"UPDATE coupons SET {', '.join(updates)} WHERE id = %s", vals)
    return {"message": "更新成功"}

@router.delete("/{coupon_id}")
async def delete_coupon(coupon_id: str):
    from app.database import get_db_cursor
    with get_db_cursor() as cur:
        cur.execute("DELETE FROM coupons WHERE id = %s", (coupon_id,))
    return {"message": "删除成功"}

@router.post("/{coupon_id}/push")
async def push_coupon_ai(coupon_id: str):
    from app.database import get_db_cursor
    import json, httpx, os
    with get_db_cursor() as cur:
        cur.execute("SELECT * FROM coupons WHERE id = %s", (coupon_id,))
        r = cur.fetchone()
        if not r:
            raise HTTPException(status_code=404, detail="优惠券不存在")
        cur.execute("""SELECT id, nickname, total_spent, order_count FROM users
                       WHERE (total_spent > 0 OR order_count > 0) ORDER BY total_spent DESC LIMIT 50""")
        users = cur.fetchall()
    api_key = os.getenv("MINIMAX_API_KEY", "")
    if not api_key:
        return {"message": "AI功能暂未配置API Key", "target_count": len(users)}
    prompt = f"""你是小吉微商城的运营专家。请从以下高价值用户中筛选出最适合领取这张优惠券的用户：
    优惠券：{r['name']}，满{r['min_order_amount']}减{r['discount_amount']}元，总量{r['total_count']}张
    用户列表（按消费金额排序）：{json.dumps(users, ensure_ascii=False)}
    请给出TOP10最有可能使用的用户ID列表，以及推荐理由。用JSON格式输出：{{"top_users": [{"id": "xxx", "reason": "..."}]}}"""
    try:
        resp = httpx.post("https://api.minimaxi.com/v1/text/chatcompletion_v2",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={"model": "MiniMax-Text-01", "messages": [{"role": "user", "content": prompt}]},
            timeout=30.0)
        content = resp.json().get("choices", [{}])[0].get("message", {}).get("content", "")
        return {"message": "AI分析完成", "analysis": content, "target_count": len(users)}
    except Exception as e:
        return {"message": f"AI分析失败：{str(e)}", "target_count": len(users)}
