"""
JWT认证依赖 - 从请求头提取并验证JWT token
"""
from fastapi import Depends, HTTPException, Header
from typing import Optional
from jose import JWTError, jwt
from app.config import settings
from app.utils.response import error_response


async def get_current_user(authorization: Optional[str] = Header(None, alias="Authorization")) -> dict:
    if authorization is None:
        raise HTTPException(status_code=401, detail=error_response(1002, "登录失效，请重新登录"))

    parts = authorization.split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise HTTPException(status_code=401, detail=error_response(1002, "无效的认证格式"))

    token = parts[1]
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
        user_id = payload.get("sub")
        username = payload.get("username", "")
        if user_id is None:
            raise HTTPException(status_code=401, detail=error_response(1002, "无效的认证信息"))
        return {"user_id": user_id, "username": username}
    except JWTError:
        raise HTTPException(status_code=401, detail=error_response(1002, "Token已过期"))


def create_access_token(user_id: str, username: str = "") -> str:
    from datetime import datetime, timedelta
    expire = datetime.utcnow() + timedelta(days=settings.access_token_expire_days)
    payload = {"sub": user_id, "username": username, "exp": expire}
    return jwt.encode(payload, settings.secret_key, algorithm=settings.algorithm)
