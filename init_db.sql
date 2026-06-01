-- =====================================================
-- 小吉微商城 - 数据库初始化脚本
-- 数据库：PostgreSQL
-- 创建时间：2026-05-28
-- =====================================================
-- 1. 开启扩展
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
-- 2. 用户表
CREATE TABLE IF NOT EXISTS users (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    openid VARCHAR(64) UNIQUE NOT NULL,
    nickname VARCHAR(64) DEFAULT '',
    avatar_url VARCHAR(256) DEFAULT '',
    phone VARCHAR(20) DEFAULT '',
    member_level VARCHAR(20) DEFAULT 'normal',
    total_points INT DEFAULT 0,
    available_points INT DEFAULT 0,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX idx_users_openid ON users(openid);
CREATE INDEX idx_users_phone ON users(phone);
-- 3. 收货地址表
CREATE TABLE IF NOT EXISTS addresses (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    receiver_name VARCHAR(64) NOT NULL,
    phone VARCHAR(20) NOT NULL,
    province VARCHAR(32) NOT NULL,
    city VARCHAR(32) NOT NULL,
    district VARCHAR(32) NOT NULL,
    detail_address VARCHAR(256) NOT NULL,
    is_default BOOLEAN DEFAULT false,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX idx_addresses_user_id ON addresses(user_id);
-- 4. 商品分类表
CREATE TABLE IF NOT EXISTS categories (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name VARCHAR(64) NOT NULL,
    icon_url VARCHAR(256) DEFAULT '',
    sort_order INT DEFAULT 0,
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
-- 5. 商品表
CREATE TABLE IF NOT EXISTS products (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    category_id UUID REFERENCES categories(id),
    name VARCHAR(128) NOT NULL,
    subtitle VARCHAR(256) DEFAULT '',
    description TEXT DEFAULT '',
    price DECIMAL(10,2) NOT NULL,
    original_price DECIMAL(10,2) DEFAULT 0,
    stock INT DEFAULT 0,
    images JSONB DEFAULT '[]'::jsonb,
    detail_images JSONB DEFAULT '[]'::jsonb,
    is_on_sale BOOLEAN DEFAULT true,
    sales_count INT DEFAULT 0,
    rating DECIMAL(2,1) DEFAULT 5.0,
    specs JSONB DEFAULT '[]'::jsonb,
    tags JSONB DEFAULT '[]'::jsonb,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX idx_products_category_id ON products(category_id);
CREATE INDEX idx_products_is_on_sale ON products(is_on_sale);
CREATE INDEX idx_products_created_at ON products(created_at DESC);
-- 6. 优惠券表
CREATE TABLE IF NOT EXISTS coupons (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name VARCHAR(64) NOT NULL,
    type VARCHAR(20) NOT NULL,
    discount_amount DECIMAL(10,2) DEFAULT 0,
    min_order_amount DECIMAL(10,2) DEFAULT 0,
    total_count INT NOT NULL,
    remain_count INT NOT NULL,
    start_time TIMESTAMP NOT NULL,
    end_time TIMESTAMP NOT NULL,
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
-- 7. 用户优惠券表
CREATE TABLE IF NOT EXISTS user_coupons (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    coupon_id UUID NOT NULL REFERENCES coupons(id) ON DELETE CASCADE,
    status VARCHAR(20) DEFAULT 'unused',
    order_id UUID REFERENCES orders(id),
    used_at TIMESTAMP,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX idx_user_coupons_user_status ON user_coupons(user_id, status);
-- 8. 订单表
CREATE TABLE IF NOT EXISTS orders (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    order_no VARCHAR(32) UNIQUE NOT NULL,
    user_id UUID NOT NULL REFERENCES users(id),
    address_id UUID REFERENCES addresses(id),
    receiver_name VARCHAR(64) DEFAULT '',
    receiver_phone VARCHAR(20) DEFAULT '',
    shipping_address VARCHAR(512) DEFAULT '',
    total_amount DECIMAL(10,2) NOT NULL,
    freight_amount DECIMAL(10,2) DEFAULT 0,
    coupon_amount DECIMAL(10,2) DEFAULT 0,
    points_amount DECIMAL(10,2) DEFAULT 0,
    pay_amount DECIMAL(10,2) NOT NULL,
    points_earned INT DEFAULT 0,
    points_used INT DEFAULT 0,
    delivery_type VARCHAR(20) NOT NULL,
    delivery_no VARCHAR(64) DEFAULT '',
    delivery_company VARCHAR(32) DEFAULT '',
    status VARCHAR(20) NOT NULL,
    pay_time TIMESTAMP,
    deliver_time TIMESTAMP,
    receive_time TIMESTAMP,
    buyer_note VARCHAR(256) DEFAULT '',
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX idx_orders_order_no ON orders(order_no);
CREATE INDEX idx_orders_user_status ON orders(user_id, status);
CREATE INDEX idx_orders_created_at ON orders(created_at DESC);
-- 9. 订单商品表
CREATE TABLE IF NOT EXISTS order_items (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    order_id UUID NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
    product_id UUID REFERENCES products(id),
    product_name VARCHAR(128) NOT NULL,
    product_image VARCHAR(256) NOT NULL,
    sku_spec JSONB DEFAULT '{}'::jsonb,
    price DECIMAL(10,2) NOT NULL,
    quantity INT NOT NULL,
    subtotal DECIMAL(10,2) NOT NULL
);
CREATE INDEX idx_order_items_order_id ON order_items(order_id);
-- 10. 收藏表
CREATE TABLE IF NOT EXISTS favorites (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    product_id UUID NOT NULL REFERENCES products(id) ON DELETE CASCADE,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id, product_id)
);
CREATE INDEX idx_favorites_user_product ON favorites(user_id, product_id);
-- 11. 积分记录表
CREATE TABLE IF NOT EXISTS points_log (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL REFERENCES users(id),
    order_id UUID REFERENCES orders(id),
    type VARCHAR(20) NOT NULL,
    points INT NOT NULL,
    balance INT NOT NULL,
    note VARCHAR(128) DEFAULT '',
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX idx_points_log_user_id ON points_log(user_id);
CREATE INDEX idx_points_log_created_at ON points_log(created_at DESC);
-- 12. 轮播图表
CREATE TABLE IF NOT EXISTS banners (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    title VARCHAR(128) NOT NULL,
    image_url VARCHAR(256) NOT NULL,
    link_type VARCHAR(20) DEFAULT 'none',
    link_value VARCHAR(256) DEFAULT '',
    sort_order INT DEFAULT 0,
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
-- 13. 购物车表
CREATE TABLE IF NOT EXISTS cart_items (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    product_id UUID NOT NULL REFERENCES products(id) ON DELETE CASCADE,
    quantity INT NOT NULL DEFAULT 1,
    sku_spec JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX idx_cart_items_user_id ON cart_items(user_id);
-- 初始化数据
INSERT INTO categories (id, name, icon_url, sort_order) VALUES
    (uuid_generate_v4(), '海南黄花梨', '/assets/icons/huanghuali.png', 1),
    (uuid_generate_v4(), '海南沉香', '/assets/icons/chenxiang.png', 2),
    (uuid_generate_v4(), '木制工艺品', '/assets/icons/woodwork.png', 3);
INSERT INTO banners (title, image_url, sort_order) VALUES
    ('海南黄花梨专场', '/assets/banners/banner1.jpg', 1),
    ('新品上市', '/assets/banners/banner2.jpg', 2),
    ('限时优惠', '/assets/banners/banner3.jpg', 3);
