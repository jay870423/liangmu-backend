"""
统一响应工具函数
"""
from typing import Any, Optional


def success_response(data: Any = None, message: str = "success"):
    return {"code": 0, "message": message, "data": data}


def error_response(code: int, message: str):
    return {"code": code, "message": message, "data": None}


def page_response(items: list, total: int, page: int, page_size: int):
    return {"items": items, "total": total, "page": page, "page_size": page_size}
