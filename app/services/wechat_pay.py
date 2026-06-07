import base64
import time
import uuid
from decimal import Decimal, ROUND_HALF_UP
from typing import Dict, Optional

import httpx
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.config import settings


WECHAT_PAY_HOST = "https://api.mch.weixin.qq.com"
_platform_cert_cache: Dict[str, object] = {}
_platform_cert_loaded_at = 0.0


class WechatPayError(Exception):
    pass


def _required_config() -> None:
    missing = [
        name for name, value in {
            "WECHAT_PAY_APPID": settings.wechat_pay_appid or settings.wechat_appid,
            "WECHAT_PAY_MCH_ID": settings.wechat_pay_mch_id,
            "WECHAT_PAY_SERIAL_NO": settings.wechat_pay_serial_no,
            "WECHAT_PAY_API_V3_KEY": settings.wechat_pay_api_v3_key,
            "WECHAT_PAY_PRIVATE_KEY_PATH": settings.wechat_pay_private_key_path,
            "WECHAT_PAY_NOTIFY_URL": settings.wechat_pay_notify_url,
        }.items()
        if not value
    ]
    if missing:
        raise WechatPayError(f"WeChat Pay config missing: {', '.join(missing)}")


def _load_private_key():
    _required_config()
    try:
        with open(settings.wechat_pay_private_key_path, "rb") as f:
            return serialization.load_pem_private_key(f.read(), password=None)
    except Exception as exc:
        raise WechatPayError("Failed to load WeChat Pay private key") from exc


def _rsa_sign(message: str) -> str:
    private_key = _load_private_key()
    signature = private_key.sign(
        message.encode("utf-8"),
        padding.PKCS1v15(),
        hashes.SHA256(),
    )
    return base64.b64encode(signature).decode("utf-8")


def _authorization(method: str, url_path: str, body: str = "") -> str:
    timestamp = str(int(time.time()))
    nonce = uuid.uuid4().hex
    message = f"{method}\n{url_path}\n{timestamp}\n{nonce}\n{body}\n"
    signature = _rsa_sign(message)
    return (
        'WECHATPAY2-SHA256-RSA2048 '
        f'mchid="{settings.wechat_pay_mch_id}",'
        f'nonce_str="{nonce}",'
        f'signature="{signature}",'
        f'timestamp="{timestamp}",'
        f'serial_no="{settings.wechat_pay_serial_no}"'
    )


def _headers(method: str, url_path: str, body: str = "") -> dict:
    return {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "Authorization": _authorization(method, url_path, body),
        "Wechatpay-Serial": settings.wechat_pay_serial_no,
    }


def amount_to_fen(amount) -> int:
    value = Decimal(str(amount or "0")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return int((value * 100).to_integral_value(rounding=ROUND_HALF_UP))


def _decrypt_resource(resource: dict) -> bytes:
    if not resource:
        raise WechatPayError("Missing encrypted resource")
    if resource.get("algorithm") != "AEAD_AES_256_GCM":
        raise WechatPayError("Unsupported encrypt algorithm")
    ciphertext = base64.b64decode(resource["ciphertext"])
    nonce = resource["nonce"].encode("utf-8")
    associated_data = (resource.get("associated_data") or "").encode("utf-8")
    aesgcm = AESGCM(settings.wechat_pay_api_v3_key.encode("utf-8"))
    return aesgcm.decrypt(nonce, ciphertext, associated_data)


async def jsapi_prepay(order_no: str, amount, openid: str, description: Optional[str] = None) -> dict:
    _required_config()
    total = amount_to_fen(amount)
    if total <= 0:
        raise WechatPayError("Pay amount must be greater than 0")
    if not openid:
        raise WechatPayError("User openid is required")

    import json
    url_path = "/v3/pay/transactions/jsapi"
    body_dict = {
        "appid": settings.wechat_pay_appid or settings.wechat_appid,
        "mchid": settings.wechat_pay_mch_id,
        "description": (description or f"Liangmu order {order_no}")[:127],
        "out_trade_no": order_no,
        "notify_url": settings.wechat_pay_notify_url,
        "amount": {"total": total, "currency": "CNY"},
        "payer": {"openid": openid},
    }
    body = json.dumps(body_dict, ensure_ascii=False, separators=(",", ":"))
    async with httpx.AsyncClient(timeout=20) as client:
        resp = await client.post(
            f"{WECHAT_PAY_HOST}{url_path}",
            content=body.encode("utf-8"),
            headers=_headers("POST", url_path, body),
        )
    if resp.status_code >= 400:
        raise WechatPayError(f"WeChat prepay failed: {resp.status_code} {resp.text[:300]}")

    prepay_id = resp.json().get("prepay_id")
    if not prepay_id:
        raise WechatPayError("WeChat prepay response missing prepay_id")

    package = f"prepay_id={prepay_id}"
    timestamp = str(int(time.time()))
    nonce = uuid.uuid4().hex
    appid = settings.wechat_pay_appid or settings.wechat_appid
    pay_sign = _rsa_sign(f"{appid}\n{timestamp}\n{nonce}\n{package}\n")
    return {
        "timeStamp": timestamp,
        "nonceStr": nonce,
        "package": package,
        "signType": "RSA",
        "paySign": pay_sign,
    }


async def _load_platform_certs(force: bool = False) -> None:
    global _platform_cert_loaded_at
    if _platform_cert_cache and not force and time.time() - _platform_cert_loaded_at < 12 * 60 * 60:
        return

    url_path = "/v3/certificates"
    async with httpx.AsyncClient(timeout=20) as client:
        resp = await client.get(f"{WECHAT_PAY_HOST}{url_path}", headers=_headers("GET", url_path, ""))
    if resp.status_code >= 400:
        raise WechatPayError(f"WeChat certificate fetch failed: {resp.status_code} {resp.text[:300]}")

    certs = {}
    for item in resp.json().get("data", []):
        serial_no = item.get("serial_no")
        cert_pem = _decrypt_resource(item.get("encrypt_certificate") or {})
        cert = x509.load_pem_x509_certificate(cert_pem)
        certs[serial_no] = cert.public_key()
    if not certs:
        raise WechatPayError("No WeChat platform certificates loaded")
    _platform_cert_cache.clear()
    _platform_cert_cache.update(certs)
    _platform_cert_loaded_at = time.time()


async def verify_notify_signature(headers: dict, body: bytes) -> None:
    timestamp = headers.get("Wechatpay-Timestamp") or headers.get("wechatpay-timestamp")
    nonce = headers.get("Wechatpay-Nonce") or headers.get("wechatpay-nonce")
    signature = headers.get("Wechatpay-Signature") or headers.get("wechatpay-signature")
    serial = headers.get("Wechatpay-Serial") or headers.get("wechatpay-serial")
    if not all([timestamp, nonce, signature, serial]):
        raise WechatPayError("Missing WeChat Pay notify headers")

    await _load_platform_certs()
    public_key = _platform_cert_cache.get(serial)
    if public_key is None:
        await _load_platform_certs(force=True)
        public_key = _platform_cert_cache.get(serial)
    if public_key is None:
        raise WechatPayError("Unknown WeChat platform certificate serial")

    message = f"{timestamp}\n{nonce}\n{body.decode('utf-8')}\n".encode("utf-8")
    try:
        public_key.verify(
            base64.b64decode(signature),
            message,
            padding.PKCS1v15(),
            hashes.SHA256(),
        )
    except Exception as exc:
        raise WechatPayError("Invalid WeChat Pay notify signature") from exc


def decrypt_notify_resource(resource: dict) -> dict:
    import json
    plaintext = _decrypt_resource(resource)
    return json.loads(plaintext.decode("utf-8"))
