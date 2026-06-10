from datetime import datetime
import uuid


def ensure_notification_tables(cursor):
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS notifications (
            id UUID PRIMARY KEY,
            type VARCHAR(32) NOT NULL DEFAULT 'system',
            title VARCHAR(120) NOT NULL,
            content TEXT NOT NULL DEFAULT '',
            target_type VARCHAR(16) NOT NULL DEFAULT 'all',
            user_id UUID NULL,
            link_type VARCHAR(32) NOT NULL DEFAULT 'none',
            link_value VARCHAR(255) NOT NULL DEFAULT '',
            is_active BOOLEAN NOT NULL DEFAULT TRUE,
            publish_at TIMESTAMP NOT NULL DEFAULT NOW(),
            created_at TIMESTAMP NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMP NOT NULL DEFAULT NOW()
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS user_notification_reads (
            id UUID PRIMARY KEY,
            notification_id UUID NOT NULL,
            user_id UUID NOT NULL,
            read_at TIMESTAMP NOT NULL DEFAULT NOW(),
            UNIQUE(notification_id, user_id)
        )
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_notifications_publish ON notifications (is_active, publish_at DESC)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_notifications_user ON notifications (target_type, user_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_notification_reads_user ON user_notification_reads (user_id, notification_id)")


def create_notification(
    cursor,
    *,
    title: str,
    content: str = "",
    type: str = "system",
    target_type: str = "all",
    user_id: str = None,
    link_type: str = "none",
    link_value: str = "",
    is_active: bool = True,
    publish_at=None,
) -> str:
    ensure_notification_tables(cursor)
    notification_id = str(uuid.uuid4())
    cursor.execute(
        """
        INSERT INTO notifications (
            id, type, title, content, target_type, user_id, link_type, link_value,
            is_active, publish_at, created_at, updated_at
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW(), NOW())
        """,
        (
            notification_id,
            type or "system",
            title,
            content or "",
            target_type or "all",
            user_id,
            link_type or "none",
            link_value or "",
            is_active,
            publish_at or datetime.now(),
        ),
    )
    return notification_id


def create_payment_success_notification(cursor, *, user_id: str, order_id: str, order_no: str, amount) -> str:
    amount_text = f"{float(amount or 0):.2f}"
    return create_notification(
        cursor,
        title="支付完成通知",
        content=f"您的订单 {order_no} 已支付成功，实付金额 ¥{amount_text}。商家将尽快为您处理发货。",
        type="payment",
        target_type="user",
        user_id=user_id,
        link_type="order",
        link_value=order_id,
    )
