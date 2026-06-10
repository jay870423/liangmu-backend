import uuid

from fastapi import APIRouter, Depends
from psycopg2.extras import RealDictCursor

from app.api.deps import get_current_user
from app.database import get_db, get_db_cursor
from app.services.notification_service import ensure_notification_tables
from app.utils.response import error_response, page_response, success_response


router = APIRouter()


def _serialize_notification(row):
    return {
        "id": str(row["id"]),
        "type": row["type"] or "system",
        "title": row["title"] or "",
        "content": row["content"] or "",
        "link_type": row["link_type"] or "none",
        "link_value": row["link_value"] or "",
        "is_read": bool(row.get("read_at")),
        "read_at": row["read_at"].isoformat() if row.get("read_at") else None,
        "publish_at": row["publish_at"].isoformat() if row.get("publish_at") else None,
        "created_at": row["created_at"].isoformat() if row.get("created_at") else None,
    }


@router.get("/notifications")
async def list_notifications(user: dict = Depends(get_current_user), page: int = 1, page_size: int = 20):
    user_id = user["user_id"]
    page = max(page, 1)
    page_size = min(max(page_size, 1), 50)
    offset = (page - 1) * page_size
    with get_db_cursor() as cursor:
        ensure_notification_tables(cursor)
        cursor.execute(
            """
            SELECT COUNT(*) AS total
            FROM notifications n
            WHERE n.is_active = TRUE
              AND n.publish_at <= NOW()
              AND (n.target_type = 'all' OR (n.target_type = 'user' AND n.user_id = %s))
            """,
            (user_id,),
        )
        total = cursor.fetchone()["total"]
        cursor.execute(
            """
            SELECT n.*, r.read_at
            FROM notifications n
            LEFT JOIN user_notification_reads r
              ON r.notification_id = n.id AND r.user_id = %s
            WHERE n.is_active = TRUE
              AND n.publish_at <= NOW()
              AND (n.target_type = 'all' OR (n.target_type = 'user' AND n.user_id = %s))
            ORDER BY n.publish_at DESC, n.created_at DESC
            LIMIT %s OFFSET %s
            """,
            (user_id, user_id, page_size, offset),
        )
        items = [_serialize_notification(row) for row in cursor.fetchall()]
    return success_response(data=page_response(items, total, page, page_size))


@router.get("/notifications/unread-count")
async def unread_count(user: dict = Depends(get_current_user)):
    user_id = user["user_id"]
    with get_db_cursor() as cursor:
        ensure_notification_tables(cursor)
        cursor.execute(
            """
            SELECT COUNT(*) AS count
            FROM notifications n
            LEFT JOIN user_notification_reads r
              ON r.notification_id = n.id AND r.user_id = %s
            WHERE n.is_active = TRUE
              AND n.publish_at <= NOW()
              AND (n.target_type = 'all' OR (n.target_type = 'user' AND n.user_id = %s))
              AND r.id IS NULL
            """,
            (user_id, user_id),
        )
        count = cursor.fetchone()["count"]
    return success_response(data={"count": count})


@router.put("/notifications/{notification_id}/read")
async def mark_notification_read(notification_id: str, user: dict = Depends(get_current_user)):
    user_id = user["user_id"]
    with get_db() as conn:
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        ensure_notification_tables(cursor)
        cursor.execute(
            """
            SELECT id
            FROM notifications
            WHERE id = %s
              AND is_active = TRUE
              AND publish_at <= NOW()
              AND (target_type = 'all' OR (target_type = 'user' AND user_id = %s))
            """,
            (notification_id, user_id),
        )
        if not cursor.fetchone():
            return error_response(404, "通知不存在")
        cursor.execute(
            """
            INSERT INTO user_notification_reads (id, notification_id, user_id, read_at)
            VALUES (%s, %s, %s, NOW())
            ON CONFLICT (notification_id, user_id) DO UPDATE SET read_at = EXCLUDED.read_at
            """,
            (str(uuid.uuid4()), notification_id, user_id),
        )
        conn.commit()
    return success_response(message="已读")


@router.put("/notifications/read-all")
async def mark_all_notifications_read(user: dict = Depends(get_current_user)):
    user_id = user["user_id"]
    with get_db() as conn:
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        ensure_notification_tables(cursor)
        cursor.execute(
            """
            SELECT n.id
            FROM notifications n
            LEFT JOIN user_notification_reads r
              ON r.notification_id = n.id AND r.user_id = %s
            WHERE n.is_active = TRUE
              AND n.publish_at <= NOW()
              AND (n.target_type = 'all' OR (n.target_type = 'user' AND n.user_id = %s))
              AND r.id IS NULL
            """,
            (user_id, user_id),
        )
        notification_ids = [row["id"] for row in cursor.fetchall()]
        for notification_id in notification_ids:
            cursor.execute(
                """
                INSERT INTO user_notification_reads (id, notification_id, user_id, read_at)
                VALUES (%s, %s, %s, NOW())
                ON CONFLICT (notification_id, user_id) DO UPDATE SET read_at = EXCLUDED.read_at
                """,
                (str(uuid.uuid4()), notification_id, user_id),
            )
        conn.commit()
    return success_response(message="全部已读")
