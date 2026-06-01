"""
数据库连接模块 - PostgreSQL连接池
"""
import psycopg2
from psycopg2 import pool
from psycopg2.extras import RealDictCursor
from contextlib import contextmanager
from app.config import settings

# 创建连接池（最小1个连接，最大10个连接）
connection_pool = None


def init_pool():
    """初始化连接池"""
    global connection_pool
    if connection_pool is None:
        connection_pool = pool.ThreadedConnectionPool(
            minconn=1,
            maxconn=10,
            dsn=settings.database_url
        )


def get_pool():
    """获取连接池"""
    global connection_pool
    if connection_pool is None:
        init_pool()
    return connection_pool


@contextmanager
def get_db():
    """
    数据库上下文管理器
    使用方式:
        with get_db() as db:
            db.execute("SELECT * FROM users")
    """
    pool = get_pool()
    conn = pool.getconn()
    try:
        yield conn
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        pool.putconn(conn)


@contextmanager
def get_db_cursor(dict_cursor=True):
    """
    返回字典游标的上下文管理器
    使用方式:
        with get_db_cursor() as cursor:
            cursor.execute("SELECT * FROM users WHERE id = %s", (user_id,))
            user = cursor.fetchone()
    """
    with get_db() as conn:
        cursor_factory = RealDictCursor if dict_cursor else None
        cursor = conn.cursor(cursor_factory=cursor_factory)
        try:
            yield cursor
            conn.commit()
        except Exception as e:
            conn.rollback()
            raise e
        finally:
            cursor.close()
