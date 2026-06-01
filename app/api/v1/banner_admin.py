from fastapi import APIRouter, HTTPException, UploadFile, File, Request
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime
import uuid
import os
import shutil

router = APIRouter(prefix="/admin/banners", tags=["admin-banner"])

UPLOAD_DIR = "/home/ubuntu/liangmu-admin/assets/banners"
os.makedirs(UPLOAD_DIR, exist_ok=True)

class BannerCreate(BaseModel):
    title: str
    image_url: str = ""
    link_type: str = "none"  # none/product/category/url
    link_value: str = ""
    sort_order: int = 0
    is_active: bool = True

class BannerUpdate(BaseModel):
    title: Optional[str] = None
    image_url: Optional[str] = None
    link_type: Optional[str] = None
    link_value: Optional[str] = None
    sort_order: Optional[int] = None
    is_active: Optional[bool] = None

@router.get("/")
async def list_banners():
    from app.database import get_db_cursor
    with get_db_cursor() as cur:
        cur.execute("SELECT * FROM banners ORDER BY sort_order ASC, created_at DESC")
        rows = cur.fetchall()
        return [{"id": str(r["id"]), "title": r["title"], "image_url": r["image_url"],
                 "link_type": r["link_type"], "link_value": r["link_value"],
                 "sort_order": r["sort_order"], "is_active": r["is_active"],
                 "created_at": r["created_at"].isoformat() if r["created_at"] else ""} for r in rows]

@router.post("/")
async def create_banner(req: BannerCreate):
    from app.database import get_db_cursor
    banner_id = str(uuid.uuid4())
    with get_db_cursor() as cur:
        cur.execute("""INSERT INTO banners (id, title, image_url, link_type, link_value, sort_order, is_active)
                       VALUES (%s, %s, %s, %s, %s, %s, %s)""",
                    (banner_id, req.title, req.image_url, req.link_type, req.link_value, req.sort_order, req.is_active))
    return {"id": banner_id, "message": "创建成功"}

@router.put("/{banner_id}")
async def update_banner(banner_id: str, req: BannerUpdate):
    from app.database import get_db_cursor
    with get_db_cursor() as cur:
        cur.execute("SELECT id FROM banners WHERE id = %s", (banner_id,))
        if not cur.fetchone():
            raise HTTPException(status_code=404, detail="Banner不存在")
        updates = []
        vals = []
        if req.title is not None: updates.append("title=%s"); vals.append(req.title)
        if req.image_url is not None: updates.append("image_url=%s"); vals.append(req.image_url)
        if req.link_type is not None: updates.append("link_type=%s"); vals.append(req.link_type)
        if req.link_value is not None: updates.append("link_value=%s"); vals.append(req.link_value)
        if req.sort_order is not None: updates.append("sort_order=%s"); vals.append(req.sort_order)
        if req.is_active is not None: updates.append("is_active=%s"); vals.append(req.is_active)
        if updates:
            vals.append(banner_id)
            cur.execute(f"UPDATE banners SET {', '.join(updates)} WHERE id = %s", vals)
    return {"message": "更新成功"}

@router.delete("/{banner_id}")
async def delete_banner(banner_id: str):
    from app.database import get_db_cursor
    with get_db_cursor() as cur:
        cur.execute("DELETE FROM banners WHERE id = %s", (banner_id,))
    return {"message": "删除成功"}

@router.post("/upload")
async def upload_banner(file: UploadFile = File(...)):
    ext = file.filename.split(".")[-1] if "." in file.filename else "jpg"
    filename = f"{uuid.uuid4().hex}.{ext}"
    path = os.path.join(UPLOAD_DIR, filename)
    with open(path, "wb") as f:
        shutil.copyfileobj(file.file, f)
    return {"url": f"/assets/banners/{filename}"}
