"""配置文件"""
import json
import os
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    database_url: str = "postgresql://liangmu:liangmu123@localhost:5432/liangmu"
    secret_key: str = "xiaoji-secret-key-2026"
    algorithm: str = "HS256"
    access_token_expire_days: int = 7
    wechat_appid: str = ""
    wechat_secret: str = ""
    wechat_pay_appid: str = ""
    wechat_pay_mch_id: str = ""
    wechat_pay_serial_no: str = ""
    wechat_pay_api_v3_key: str = ""
    wechat_pay_private_key_path: str = ""
    wechat_pay_notify_url: str = ""
    wechat_pay_public_key_id: str = ""
    wechat_pay_public_key_path: str = ""
    cors_origins: str = '["*"]'
    upload_dir: str = "./uploads"
    max_file_size: int = 10485760

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"

    @property
    def cors_origins_list(self) -> list:
        if isinstance(self.cors_origins, str):
            return json.loads(self.cors_origins)
        return self.cors_origins

settings = Settings()
os.makedirs(settings.upload_dir, exist_ok=True)
