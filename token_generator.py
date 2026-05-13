# token_generator.py
# Fixed for httpx==0.24.1

import json
import base64
import httpx
import os
from datetime import datetime
from Crypto.Cipher import AES
from google.protobuf import json_format
from typing import Dict, Any

freefire_pb2    = None
PROTO_AVAILABLE = False

try:
    from ff_proto import freefire_pb2
    PROTO_AVAILABLE = True
    print("[Token] Protobuf loaded OK")
except ImportError:
    PROTO_AVAILABLE = False
    print("[Token] WARNING: Protobuf not available")

TOKEN_FILE    = "accounts_with_tokens.json"
OAUTH_URL     = "https://ffmconnect.live.gop.garenanow.com/api/v2/oauth/guest/token:grant"
MAJOR_LOGIN   = "https://loginbp.ggwhitehawk.com/MajorLogin"
CLIENT_ID     = 100067
CLIENT_SECRET = "2ee44819e9b4598845141067b281621874d0d5d7af9d8f7e00c1e54715b7d1e3"
RELEASE_VER   = "OB53"
TIMEOUT       = 15.0

MAIN_KEY = base64.b64decode("WWcmdGMlREV1aDYlWmNeOA==")
MAIN_IV  = base64.b64decode("Nm95WkRyMjJFM3ljaGpNJQ==")

DALVIK_UA = [
    "Dalvik/2.1.0 (Linux; U; Android 14; SM-S918B Build/UP1A.231005.007)",
    "Dalvik/2.1.0 (Linux; U; Android 13; 2201116SG Build/TKQ1.220829.002)",
    "Dalvik/2.1.0 (Linux; U; Android 13; NE2210 Build/RKQ1.211119.001)",
]


def pkcs7_pad(data: bytes) -> bytes:
    pad_len = 16 - (len(data) % 16)
    return data + bytes([pad_len] * pad_len)


def aes_encrypt(plaintext: bytes) -> bytes:
    cipher = AES.new(MAIN_KEY, AES.MODE_CBC, MAIN_IV)
    return cipher.encrypt(pkcs7_pad(plaintext))


def decode_jwt_field(token: str, field: str, default=None):
    try:
        if '.' not in token:
            return default
        payload  = token.split('.')[1]
        payload += '=' * (-len(payload) % 4)
        decoded  = base64.urlsafe_b64decode(payload)
        data     = json.loads(decoded)
        return data.get(field, default)
    except Exception:
        return default


async def process_uid_pwd_with_token(uid: str, pwd: str) -> Dict[str, Any] | None:
    """Full token generation pipeline"""
    try:
        # Use direct connection for token generation (no proxy needed)
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(TIMEOUT),
            follow_redirects=True
        ) as client:

            # ── Step 1: OAuth ─────────────────────────────────
            oauth_payload = {
                "client_id":     CLIENT_ID,
                "client_secret": CLIENT_SECRET,
                "client_type":   2,
                "password":      pwd,
                "response_type": "token",
                "uid":           int(uid),
            }
            oauth_headers = {
                "User-Agent":      "GarenaMSDK/4.0.19P10",
                "Content-Type":    "application/json; charset=utf-8",
                "Accept":          "application/json",
                "Accept-Encoding": "gzip",
                "Connection":      "Keep-Alive",
            }

            oauth_resp = await client.post(
                OAUTH_URL,
                json=oauth_payload,
                headers=oauth_headers
            )

            if oauth_resp.status_code != 200:
                print(f"[Token] OAuth failed: {oauth_resp.status_code}")
                return None

            oauth_data   = oauth_resp.json().get("data", {})
            access_token = oauth_data.get("access_token", "")
            open_id      = oauth_data.get("open_id", "")

            if not access_token:
                print(f"[Token] No access_token in OAuth response")
                return None

            print(f"[Token] OAuth OK, open_id={open_id[:10]}...")

            # ── Step 2: MajorLogin with Protobuf ─────────────
            if not PROTO_AVAILABLE:
                print("[Token] Protobuf unavailable — skip JWT")
                return None

            req_msg = freefire_pb2.LoginReq()
            json_format.ParseDict({
                "open_id":             
