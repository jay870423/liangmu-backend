"""
FastAPI主入口 - 小吉微商城后端
"""
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from app.config import settings
from app.database import init_pool
from app.api.v1 import router as v1_router
import logging, os

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="小吉微商城API",
    version="1.0.0",
    description="海南木质工艺品微商城后端API",
    docs_url="/docs",
    redoc_url="/redoc"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"全局异常: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"code": 500, "message": f"服务器内部错误: {str(exc)}", "data": None}
    )

@app.on_event("startup")
async def startup_event():
    logger.info("正在初始化数据库连接池...")
    init_pool()
    logger.info("数据库连接池初始化完成")
    # 确保上传目录存在
    upload_dir = os.path.join(os.path.dirname(__file__), "static", "uploads")
    os.makedirs(upload_dir, exist_ok=True)
    logger.info(f"上传目录已创建: {upload_dir}")

@app.on_event("shutdown")
async def shutdown_event():
    logger.info("正在关闭数据库连接池...")
    from app.database import connection_pool
    if connection_pool:
        connection_pool.closeall()
    logger.info("数据库连接池已关闭")

app.include_router(v1_router, prefix="/api/v1")

# 挂载静态文件目录（商品图片等上传文件）
static_dir = "/home/ubuntu/liangmu-forest/backend/static"
if os.path.exists(static_dir):
    app.mount("/static", StaticFiles(directory=static_dir), name="static")
    logger.info(f"静态文件目录已挂载: {static_dir}")

@app.get("/health")
async def health_check():
    return {"status": "healthy", "version": "1.0.0", "service": "liangmu-forest-api"}

@app.get("/")
async def root():
    return {"message": "小吉微商城API", "version": "1.0.0"}
