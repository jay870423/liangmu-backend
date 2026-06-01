"""
API v1 路由汇总注册
"""
from fastapi import APIRouter
from app.api.v1 import user, product, category, cart, order, coupon, points, address, favorite, home

router = APIRouter()

router.include_router(user.router, tags=["用户模块"])
router.include_router(product.router, tags=["商品模块"])
router.include_router(category.router, tags=["分类模块"])
router.include_router(cart.router, tags=["购物车模块"])
router.include_router(order.router, tags=["订单模块"])
router.include_router(coupon.router, tags=["优惠券模块"])
router.include_router(points.router, tags=["积分模块"])
router.include_router(address.router, tags=["地址模块"])
router.include_router(favorite.router, tags=["收藏模块"])
router.include_router(home.router, tags=["首页模块"])
