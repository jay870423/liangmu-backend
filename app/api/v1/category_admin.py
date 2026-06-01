from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
import uuid

router = APIRouter(prefix="/admin/categories", tags=["admin-category"])

class CategoryCreate(BaseModel):
    name: str
    icon_url: str = ""
    sort_order: int = 0
    is_active: bool = True

class CategoryUpdate(BaseModel):
    name: Optional[str] = None
    icon_url: Optional[str] = None
    sort_order: Optional[int] = None
    is_active: Optional[bool] = None

@router.get("/")
async def list_categories():
    from app.database import get_db_cursor
    with get_db_cursor() as cur:
        cur.execute("SELECT id, name, icon_url, sort_order, is_active FROM categories ORDER BY sort_order ASC, created_at ASC")
        rows = cur.fetchall()
        items = [{
            "id": str(r["id"]),
            "name": r["name"],
            "icon_url": r["icon_url"] or "",
            "sort_order": r["sort_order"],
            "is_active": r["is_active"]
        } for r in rows]
        return {"items": items, "total": len(items)}

@router.post("/")
async def create_category(req: CategoryCreate):
    from app.database import get_db_cursor
    cat_id = str(uuid.uuid4())
    with get_db_cursor() as cur:
        cur.execute("""INSERT INTO categories (id, name, icon_url, sort_order, is_active)
                       VALUES (%s, %s, %s, %s, %s)""",
                    (cat_id, req.name, req.icon_url, req.sort_order, req.is_active))
    return {"id": cat_id, "message": "创建成功"}

@router.put("/{category_id}")
async def update_category(category_id: str, req: CategoryUpdate):
    from app.database import get_db_cursor
    with get_db_cursor() as cur:
        cur.execute("SELECT id FROM categories WHERE id = %s", (category_id,))
        if not cur.fetchone():
            raise HTTPException(status_code=404, detail="分类不存在")
        updates = []
        vals = []
        if req.name is not None: updates.append("name=%s"); vals.append(req.name)
        if req.icon_url is not None: updates.append("icon_url=%s"); vals.append(req.icon_url)
        if req.sort_order is not None: updates.append("sort_order=%s"); vals.append(req.sort_order)
        if req.is_active is not None: updates.append("is_active=%s"); vals.append(req.is_active)
        if updates:
            vals.append(category_id)
            cur.execute(f"UPDATE categories SET {', '.join(updates)} WHERE id = %s", vals)
    return {"message": "更新成功"}

@router.delete("/{category_id}")
async def delete_category(category_id: str):
    from app.database import get_db_cursor
    with get_db_cursor() as cur:
        # 检查是否有商品关联
        cur.execute("SELECT COUNT(*) as cnt FROM products WHERE category_id = %s", (category_id,))
        cnt = cur.fetchone()["cnt"]
        if cnt > 0:
            raise HTTPException(status_code=400, detail=f"该分类下有{cnt}件商品，无法删除")
        cur.execute("DELETE FROM categories WHERE id = %s", (category_id,))
    return {"message": "删除成功"}
