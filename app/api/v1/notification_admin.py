from datetime import datetime
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from psycopg2.extras import RealDictCursor

from app.database import get_db, get_db_cursor
from app.services.notification_service import create_notification, ensure_notification_tables


router = APIRouter(prefix="/admin/notifications", tags=["admin-notification"])


class NotificationCreate(BaseModel):
    title: str
    content: str = ""
    type: str = "activity"
    target_type: str = "all"
    user_id: Optional[str] = None
    link_type: str = "none"
    link_value: str = ""
    is_active: bool = True
    publish_at: Optional[str] = None


class NotificationUpdate(BaseModel):
    title: Optional[str] = None
    content: Optional[str] = None
    type: Optional[str] = None
    target_type: Optional[str] = None
    user_id: Optional[str] = None
    link_type: Optional[str] = None
    link_value: Optional[str] = None
    is_active: Optional[bool] = None
    publish_at: Optional[str] = None


def _parse_time(value):
    if not value:
        return datetime.now()
    text = str(value).strip()
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).replace(tzinfo=None)
    except ValueError:
        try:
            return datetime.strptime(text, "%Y-%m-%d %H:%M:%S")
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="发布时间格式不正确") from exc


def _validate_payload(payload):
    if payload.title is not None and not payload.title.strip():
        raise HTTPException(status_code=400, detail="请填写通知标题")
    target_type = payload.target_type or "all"
    if target_type not in ("all", "user"):
        raise HTTPException(status_code=400, detail="通知对象不正确")
    if target_type == "user" and not payload.user_id:
        raise HTTPException(status_code=400, detail="请选择指定用户")
    link_type = payload.link_type or "none"
    if link_type not in ("none", "product", "category", "url", "order"):
        raise HTTPException(status_code=400, detail="跳转类型不正确")
    if link_type != "none" and not (payload.link_value or "").strip():
        raise HTTPException(status_code=400, detail="请填写跳转目标")


def _row_to_item(row):
    return {
        "id": str(row["id"]),
        "type": row["type"] or "system",
        "title": row["title"] or "",
        "content": row["content"] or "",
        "target_type": row["target_type"] or "all",
        "user_id": str(row["user_id"]) if row.get("user_id") else "",
        "link_type": row["link_type"] or "none",
        "link_value": row["link_value"] or "",
        "is_active": bool(row["is_active"]),
        "publish_at": row["publish_at"].isoformat() if row.get("publish_at") else "",
        "created_at": row["created_at"].isoformat() if row.get("created_at") else "",
        "read_count": row.get("read_count") or 0,
    }


@router.get("/")
async def list_admin_notifications(page: int = 1, page_size: int = 10, keyword: str = None, type: str = None):
    page = max(page, 1)
    page_size = min(max(page_size, 1), 50)
    offset = (page - 1) * page_size
    conditions = []
    params = []
    if keyword and keyword.strip():
        like = f"%{keyword.strip()}%"
        conditions.append("(title ILIKE %s OR content ILIKE %s OR link_value ILIKE %s)")
        params.extend([like, like, like])
    if type and type != "all":
        conditions.append("type = %s")
        params.append(type)
    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    with get_db_cursor() as cursor:
        ensure_notification_tables(cursor)
        cursor.execute(f"SELECT COUNT(*) AS total FROM notifications {where}", params)
        total = cursor.fetchone()["total"]
        cursor.execute(
            f"""
            SELECT n.*,
                   (SELECT COUNT(*) FROM user_notification_reads r WHERE r.notification_id = n.id) AS read_count
            FROM notifications n
            {where}
            ORDER BY n.created_at DESC
            LIMIT %s OFFSET %s
            """,
            params + [page_size, offset],
        )
        items = [_row_to_item(row) for row in cursor.fetchall()]
    return {"items": items, "total": total}


@router.post("/")
async def create_admin_notification(req: NotificationCreate):
    _validate_payload(req)
    with get_db() as conn:
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        notification_id = create_notification(
            cursor,
            title=req.title.strip(),
            content=req.content or "",
            type=req.type or "activity",
            target_type=req.target_type or "all",
            user_id=req.user_id if req.target_type == "user" else None,
            link_type=req.link_type or "none",
            link_value=(req.link_value or "").strip(),
            is_active=req.is_active,
            publish_at=_parse_time(req.publish_at),
        )
        conn.commit()
    return {"id": notification_id, "message": "创建成功"}


@router.put("/{notification_id}")
async def update_admin_notification(notification_id: str, req: NotificationUpdate):
    _validate_payload(req)
    updates = []
    params = []
    for field in ("title", "content", "type", "target_type", "link_type", "link_value", "is_active"):
        value = getattr(req, field)
        if value is not None:
            updates.append(f"{field} = %s")
            params.append(value.strip() if isinstance(value, str) else value)
    if req.user_id is not None:
        updates.append("user_id = %s")
        params.append(req.user_id if req.target_type == "user" else None)
    if req.publish_at is not None:
        updates.append("publish_at = %s")
        params.append(_parse_time(req.publish_at))
    if not updates:
        return {"message": "没有需要更新的内容"}
    updates.append("updated_at = NOW()")
    params.append(notification_id)
    with get_db_cursor() as cursor:
        ensure_notification_tables(cursor)
        cursor.execute(f"UPDATE notifications SET {', '.join(updates)} WHERE id = %s", params)
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="通知不存在")
    return {"message": "更新成功"}


@router.delete("/{notification_id}")
async def delete_admin_notification(notification_id: str):
    with get_db_cursor() as cursor:
        ensure_notification_tables(cursor)
        cursor.execute("UPDATE notifications SET is_active = FALSE, updated_at = NOW() WHERE id = %s", (notification_id,))
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="通知不存在")
    return {"message": "删除成功"}
