"""首页模块API（小程序端 + 管理端）"""
from decimal import Decimal, ROUND_HALF_UP
from fastapi import APIRouter, HTTPException, UploadFile, File, Query
from pydantic import BaseModel
from typing import Optional, List
import uuid
import os
import shutil
import httpx

from app.utils.response import success_response
from app.database import get_db_cursor

router = APIRouter()

def money(value):
    amount = Decimal(str(value or 0)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return f"{amount:.2f}"

ASSET_UPLOAD_DIR = "/home/ubuntu/liangmu-admin/assets/uploads"
ASSET_UPLOAD_PREFIX = "/assets/uploads"
BANNER_ASPECT_RATIO = "16:9"
BANNER_SIZE_HINT = "750x420"
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

async def _save_generated_image(image_url: str, prefix: str) -> str:
    async with httpx.AsyncClient(timeout=60.0, follow_redirects=True) as client:
        resp = await client.get(image_url)
    resp.raise_for_status()
    ext = _ext_from_content_type(resp.headers.get("content-type"), ".jpg")
    filename = f"{prefix}_{uuid.uuid4().hex}{ext}"
    filepath = os.path.join(ASSET_UPLOAD_DIR, filename)
    with open(filepath, "wb") as f:
        f.write(resp.content)
    return f"{ASSET_UPLOAD_PREFIX}/{filename}"

# ============ 小程序端（只读） ============

@router.get("/home/banners")
async def get_banners():
    """小程序轮播图列表（只返回启用状态）"""
    with get_db_cursor() as cursor:
        cursor.execute("SELECT id, title, image_url, link_type, link_value FROM banners WHERE is_active = true ORDER BY sort_order ASC")
        banners = cursor.fetchall()
    items = [{"id": str(b["id"]), "title": b["title"], "image": b["image_url"] or "", "link_type": b["link_type"] or "none", "link_value": b["link_value"] or ""} for b in banners]
    return success_response(data={"items": items})

@router.get("/home/categories")
async def get_home_categories():
    """小程序分类列表（只返回启用状态）"""
    with get_db_cursor() as cursor:
        cursor.execute("SELECT id, name, icon_url, sort_order FROM categories WHERE is_active = true ORDER BY sort_order ASC")
        categories = cursor.fetchall()
    items = [{"id": str(c["id"]), "name": c["name"], "icon": c["icon_url"] or "", "sort_order": c["sort_order"]} for c in categories]
    return success_response(data={"items": items})

@router.get("/home/new")
async def get_home_new(limit: int = 10):
    with get_db_cursor() as cursor:
        cursor.execute("SELECT id, name, subtitle, price, original_price, shipping_fee, images, sales_count, rating FROM products WHERE is_on_sale = true ORDER BY created_at DESC LIMIT %s", (limit,))
        products = cursor.fetchall()
    items = []
    for p in products:
        images = p["images"] or []
        items.append({
            "id": str(p["id"]), "name": p["name"], "subtitle": p["subtitle"] or "",
            "price": money(p["price"]), "original_price": money(p["original_price"]),
            "shipping_fee": money(p["shipping_fee"]),
            "main_image": images[0] if images else "",
            "sales": p["sales_count"] or 0, "rating": float(p["rating"]) if p["rating"] else 5.0
        })
    return success_response(data={"items": items})

@router.get("/home/recommend")
async def get_home_recommend(limit: int = 10):
    with get_db_cursor() as cursor:
        cursor.execute("SELECT id, name, subtitle, price, original_price, shipping_fee, images, sales_count, rating FROM products WHERE is_on_sale = true ORDER BY RANDOM() LIMIT %s", (limit,))
        products = cursor.fetchall()
    items = []
    for p in products:
        images = p["images"] or []
        items.append({
            "id": str(p["id"]), "name": p["name"], "subtitle": p["subtitle"] or "",
            "price": money(p["price"]), "original_price": money(p["original_price"]),
            "shipping_fee": money(p["shipping_fee"]),
            "main_image": images[0] if images else "",
            "sales": p["sales_count"] or 0, "rating": float(p["rating"]) if p["rating"] else 5.0
        })
    return success_response(data={"items": items})


# ============ 管理端 - 轮播图 ============

class BannerCreate(BaseModel):
    title: str
    image_url: str = ""
    link_type: str = "none"
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

@router.get("/home/banners/list")
async def list_banners_admin():
    """管理端：获取所有轮播图（含未启用的）"""
    with get_db_cursor() as cur:
        cur.execute("SELECT * FROM banners ORDER BY sort_order ASC, created_at DESC")
        rows = cur.fetchall()
        return [{"id": str(r["id"]), "title": r["title"], "image": r["image_url"] or "",
                 "link_type": r["link_type"] or "none", "link_value": r["link_value"] or "",
                 "sort_order": r["sort_order"], "is_active": r["is_active"],
                 "created_at": r["created_at"].isoformat() if r["created_at"] else ""} for r in rows]

@router.post("/home/banners")
async def create_banner(req: BannerCreate):
    """管理端：创建轮播图"""
    banner_id = str(uuid.uuid4())
    with get_db_cursor() as cur:
        cur.execute("""INSERT INTO banners (id, title, image_url, link_type, link_value, sort_order, is_active)
                       VALUES (%s, %s, %s, %s, %s, %s, %s)""",
                    (banner_id, req.title, req.image_url, req.link_type, req.link_value, req.sort_order, req.is_active))
    return {"id": banner_id, "message": "创建成功"}

@router.put("/home/banners/{banner_id}")
async def update_banner(banner_id: str, req: BannerUpdate):
    """管理端：更新轮播图"""
    with get_db_cursor() as cur:
        cur.execute("SELECT id FROM banners WHERE id = %s", (banner_id,))
        if not cur.fetchone():
            raise HTTPException(status_code=404, detail="轮播图不存在")
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

@router.delete("/home/banners/{banner_id}")
async def delete_banner(banner_id: str):
    """管理端：删除轮播图"""
    with get_db_cursor() as cur:
        cur.execute("DELETE FROM banners WHERE id = %s", (banner_id,))
    return {"message": "删除成功"}

@router.post("/home/banners/upload")
async def upload_banner(file: UploadFile = File(...)):
    """管理端：上传轮播图图片"""
    ext = file.filename.split(".")[-1] if "." in file.filename else "jpg"
    if ext.lower() not in ["jpg", "jpeg", "png", "webp"]:
        raise HTTPException(status_code=400, detail="仅支持 jpg/png/webp 格式")
    filename = f"banner_{uuid.uuid4().hex}.{ext.lower()}"
    path = os.path.join(ASSET_UPLOAD_DIR, filename)
    with open(path, "wb") as f:
        shutil.copyfileobj(file.file, f)
    return {"url": f"{ASSET_UPLOAD_PREFIX}/{filename}"}

@router.get("/home/banners/ai/generate_image")
async def generate_banner_image(
    banner_title: str = Query(..., description="轮播图标题"),
    banner_desc: str = Query("", description="轮播图描述文案")
):
    """管理端：AI生成轮播图（Banner）"""
    api_key = os.getenv("MINIMAX_API_KEY", "")
    if not api_key:
        return {"image_url": "", "error": "API Key未配置"}
    try:
        prompt = (
            f"微信小程序商城首页轮播横幅图，主题：{banner_title}，"
            f"画面比例必须为横向 {BANNER_ASPECT_RATIO}，适配小程序轮播位 {BANNER_SIZE_HINT}，"
            "主体完整居中并横向铺开，主体上下左右都留出安全边距，不要裁切主体，"
            "构图适合手机首屏轮播展示，远看清楚，近看有细节，"
            "风格：高端木质工艺品/文玩类，清新纯色或高级木质背景，专业商业摄影，"
            "光线柔和，8K超清，无文字、无水印、无边框。"
        )
        if banner_desc:
            prompt += f" 画面描述：{banner_desc}。请严格围绕该描述生成，不要生成方图或竖图。"
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(
                "https://api.minimaxi.com/v1/image_generation",
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json={
                    "model": "image-01",
                    "prompt": prompt,
                    "aspect_ratio": BANNER_ASPECT_RATIO,
                    "n": 1,
                    "prompt_optimizer": True,
                    "response_format": "url",
                }
            )
        result = resp.json()
        image_url = result.get("data", {}).get("image_urls", [""])[0]
        if not image_url:
            return {"image_url": "", "error": "生成失败，请重试"}
        local_url = await _save_generated_image(image_url, "banner")
        return {"image_url": local_url}
    except Exception as e:
        return {"image_url": "", "error": str(e)}


# ============ 管理端 - 分类 ============

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

@router.get("/home/categories/list")
async def list_categories_admin():
    """管理端：获取所有分类"""
    with get_db_cursor() as cur:
        cur.execute("SELECT id, name, icon_url, sort_order, is_active FROM categories ORDER BY sort_order ASC, created_at ASC")
        rows = cur.fetchall()
        return {"items": [{
            "id": str(r["id"]), "name": r["name"],
            "icon_url": r["icon_url"] or "", "sort_order": r["sort_order"],
            "is_active": r["is_active"]
        } for r in rows], "total": len(rows)}

@router.post("/home/categories")
async def create_category(req: CategoryCreate):
    """管理端：创建分类"""
    cat_id = str(uuid.uuid4())
    with get_db_cursor() as cur:
        cur.execute("""INSERT INTO categories (id, name, icon_url, sort_order, is_active)
                       VALUES (%s, %s, %s, %s, %s)""",
                    (cat_id, req.name, req.icon_url, req.sort_order, req.is_active))
    return {"id": cat_id, "message": "创建成功"}

@router.put("/home/categories/{category_id}")
async def update_category(category_id: str, req: CategoryUpdate):
    """管理端：更新分类"""
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

@router.delete("/home/categories/{category_id}")
async def delete_category(category_id: str):
    """管理端：删除分类"""
    with get_db_cursor() as cur:
        cur.execute("SELECT COUNT(*) as cnt FROM products WHERE category_id = %s", (category_id,))
        cnt = cur.fetchone()["cnt"]
        if cnt > 0:
            raise HTTPException(status_code=400, detail=f"该分类下有{cnt}件商品，无法删除")
        cur.execute("DELETE FROM categories WHERE id = %s", (category_id,))
    return {"message": "删除成功"}

@router.post("/home/categories/upload")
async def upload_category_icon(file: UploadFile = File(...)):
    """管理端：上传分类图标"""
    ext = file.filename.split(".")[-1] if "." in file.filename else "png"
    if ext.lower() not in ["jpg", "jpeg", "png", "webp", "svg"]:
        raise HTTPException(status_code=400, detail="仅支持 jpg/png/svg/webp 格式")
    filename = f"category_{uuid.uuid4().hex}.{ext.lower()}"
    path = os.path.join(ASSET_UPLOAD_DIR, filename)
    with open(path, "wb") as f:
        shutil.copyfileobj(file.file, f)
    return {"url": f"{ASSET_UPLOAD_PREFIX}/{filename}"}

@router.get("/home/categories/ai/generate_icon")
async def generate_category_icon(
    category_name: str = Query(..., description="分类名称"),
    category_type: str = Query("", description="分类类型/风格")
):
    """管理端：AI生成分类图标"""
    api_key = os.getenv("MINIMAX_API_KEY", "")
    if not api_key:
        return {"icon_url": "", "error": "API Key未配置"}
    try:
        prompt = (
            f"简约分类图标，设计风格：{category_name}，"
            f"类别：木质工艺品/文玩手串，高端简约扁平化图标设计，"
            f"单色图标，透明背景，无文字，SVG矢量风格，适合电商分类导航"
        )
        if category_type:
            prompt += f"，风格：{category_type}"
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(
                "https://api.minimaxi.com/v1/image_generation",
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json={"model": "image-01", "prompt": prompt, "response_format": "url"}
            )
        result = resp.json()
        image_url = result.get("data", {}).get("image_urls", [""])[0]
        if not image_url:
            return {"icon_url": "", "error": "生成失败，请重试"}
        local_url = await _save_generated_image(image_url, "category")
        return {"icon_url": local_url}
    except Exception as e:
        return {"icon_url": "", "error": str(e)}
