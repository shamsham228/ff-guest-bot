# token_generator.py
# Generates real JWT tokens using Garena API + Protobuf + AES

import json
import base64
import asyncio
import httpx
import os
from datetime import datetime
from Crypto.Cipher import AES
from google.protobuf import json_format
from typing import Dict, Any

# ── Proto Import ──────────────────────────────────────────────────
freefire_pb2    = None
PROTO_AVAILABLE = False

try:
    from ff_proto import freefire_pb2
    PROTO_AVAILABLE = True
    print("[Token] ✅ Protobuf loaded")
except ImportError:
    PROTO_AVAILABLE = False
    print("[Token] ⚠️ Protobuf not available")

TOKEN_FILE = "accounts_with_tokens.json"

# ── Crypto Constants ──────────────────────────────────────────────
MAIN_KEY = base64.b64decode("WWcmdGMlREV1aDYlWmNeOA==")
MAIN_IV  = base64.b64decode("Nm95WkRyMjJFM3ljaGpNJQ==")

# ── API Constants ─────────────────────────────────────────────────
OAUTH_URL       = "https://ffmconnect.live.gop.garenanow.com/api/v2/oauth/guest/token:grant"
MAJOR_LOGIN_URL = "https://loginbp.ggwhitehawk.com/MajorLogin"
CLIENT_ID       = 100067
CLIENT_SECRET   = "2ee44819e9b4598845141067b281621874d0d5d7af9d8f7e00c1e54715b7d1e3"
RELEASE_VERSION = "OB53"
TIMEOUT         = 15.0

USER_AGENTS = [
    "Dalvik/2.1.0 (Linux; U; Android 14; SM-S918B Build/UP1A.231005.007)",
    "Dalvik/2.1.0 (Linux; U; Android 13; 2201116SG Build/TKQ1.220829.002)",
    "Dalvik/2.1.0 (Linux; U; Android 13; NE2210 Build/RKQ1.211119.001)",
]


def log(msg: str) -> None:
    print(f"[Token] {msg}")


def pkcs7_pad(data: bytes) -> bytes:
    """PKCS7 padding for AES"""
    pad_len = 16 - (len(data) % 16)
    return data + bytes([pad_len] * pad_len)


def aes_encrypt(plaintext: bytes) -> bytes:
    """AES-128-CBC encryption"""
    cipher = AES.new(MAIN_KEY, AES.MODE_CBC, MAIN_IV)
    return cipher.encrypt(pkcs7_pad(plaintext))


def decode_jwt_field(token: str, field: str, default=None):
    """Safely decode a field from JWT payload without verification"""
    try:
        if '.' not in token:
            return default
        payload = token.split('.')[1]
        # Fix base64 padding
        payload += '=' * (-len(payload) % 4)
        decoded  = base64.urlsafe_b64decode(payload)
        data     = json.loads(decoded)
        return data.get(field, default)
    except Exception:
        return default


async def get_oauth_token(
    client: httpx.AsyncClient,
    uid: str,
    password: str
) -> tuple[str, str, str]:
    """
    Get OAuth access token from Garena.
    Returns (access_token, open_id, garena_token)
    """
    try:
        payload = {
            "client_id":     CLIENT_ID,
            "client_secret": CLIENT_SECRET,
            "client_type":   2,
            "password":      password,
            "response_type": "token",
            "uid":           int(uid),
        }
        headers = {
            "User-Agent":      "GarenaMSDK/4.0.19P10",
            "Content-Type":    "application/json; charset=utf-8",
            "Accept":          "application/json",
            "Connection":      "Keep-Alive",
            "Accept-Encoding": "gzip",
        }

        resp = await client.post(OAUTH_URL, json=payload, headers=headers, timeout=TIMEOUT)
        resp.raise_for_status()

        data         = resp.json().get("data", {})
        access_token = data.get("access_token", "")
        open_id      = data.get("open_id", "")

        if not access_token:
            log(f"❌ No access_token in response: {resp.text[:200]}")
            return "", "", ""

        log("✅ OAuth token obtained")
        return access_token, open_id, access_token

    except Exception as e:
        log(f"❌ OAuth error: {e}")
        return "", "", ""


async def get_jwt_token(
    client: httpx.AsyncClient,
    access_token: str,
    open_id: str
) -> tuple[str, str, str, str]:
    """
    Get JWT from MajorLogin using protobuf.
    Returns (jwt_token, account_id, lock_region, server_url)
    """
    try:
        if not PROTO_AVAILABLE:
            log("❌ Protobuf not available")
            return "", "", "IND", ""

        # Build protobuf LoginReq
        req_msg = freefire_pb2.LoginReq()
        json_format.ParseDict({
            "open_id":             open_id,
            "open_id_type":        "4",
            "login_token":         access_token,
            "orign_platform_type": "4",
        }, req_msg)

        # Encrypt
        encrypted = aes_encrypt(req_msg.SerializeToString())

        headers = {
            "User-Agent":      random.choice(USER_AGENTS) if 'random' in dir() else USER_AGENTS[0],
            "Content-Type":    "application/octet-stream",
            "Connection":      "Keep-Alive",
            "Accept-Encoding": "gzip",
            "Expect":          "100-continue",
            "X-Unity-Version": "2018.4.11f1",
            "X-GA":            "v1 1",
            "ReleaseVersion":  RELEASE_VERSION,
        }

        resp = await client.post(
            MAJOR_LOGIN_URL,
            content=encrypted,
            headers=headers,
            timeout=TIMEOUT
        )
        resp.raise_for_status()

        # Decode protobuf response
        res_msg = freefire_pb2.LoginRes()
        res_msg.ParseFromString(resp.content)

        jwt        = res_msg.token       or ""
        region     = res_msg.lock_region or "IND"
        server_url = res_msg.server_url  or f"https://client.ind.freefiremobile.com"
        account_id = str(res_msg.account_id) if res_msg.account_id else ""

        if not jwt:
            log("❌ Empty JWT from MajorLogin")
            return "", account_id, region, server_url

        log(f"✅ JWT obtained (Account: {account_id})")
        return jwt, account_id, region, server_url

    except Exception as e:
        log(f"❌ JWT error: {e}")
        return "", "", "IND", ""


def save_token_to_file(uid: str, pwd: str, token_data: dict) -> None:
    """Save token to accounts_with_tokens.json"""
    try:
        # Load existing
        all_tokens: dict = {}
        if os.path.exists(TOKEN_FILE):
            try:
                with open(TOKEN_FILE, "r") as f:
                    all_tokens = json.load(f)
            except Exception:
                all_tokens = {}

        # Check duplicate
        for entry in all_tokens.values():
            if entry.get("uid") == uid or entry.get("account_id") == token_data.get("accountId"):
                log(f"⚠️ Duplicate UID {uid} — skipping save")
                return

        # Build entry
        create_time = int(datetime.now().timestamp())
        lock_region = token_data.get("lockRegion", "IND")
        idx         = len(all_tokens) + 1

        entry = {
            "uid":           uid,
            "password":      pwd,
            "account_id":    token_data.get("accountId", uid),
            "nickname":      token_data.get("nickname", ""),
            "agora_env":     "live",
            "create_time":   create_time,
            "expiry_time":   create_time + 1_296_000,  # 15 days
            "ip_region":     "IN",
            "lock_region":   lock_region,
            "noti_region":   lock_region,
            "main_platform": 4,
            "platform":      4,
            "scope":         ["get_user_info", "get_friends", "payment", "send_request"],
            "server":        token_data.get("serverUrl", "https://client.ind.freefiremobile.com"),
            "ttl":           28800,
            "data_uid":      token_data.get("accountId", uid),
            "jwt_token":     token_data.get("jwt_token", ""),
            "access_token":  token_data.get("access_token", ""),
            "status":        "✅ ACTIVE",
        }

        all_tokens[f"token_{idx}"] = entry

        with open(TOKEN_FILE, "w") as f:
            json.dump(all_tokens, f, indent=4)

        log(f"💾 Token saved → token_{idx}")

    except Exception as e:
        log(f"❌ Save error: {e}")


async def process_uid_pwd_with_token(uid: str, pwd: str) -> Dict[str, Any] | None:
    """
    Full token generation pipeline.
    Returns token data dict or None on failure.
    """
    try:
        import random as _random
        async with httpx.AsyncClient(
            timeout=TIMEOUT,
            follow_redirects=True
        ) as client:

            # Step 1: OAuth
            access_token, open_id, garena_token = await get_oauth_token(client, uid, pwd)
            if not access_token:
                return None

            # Step 2: JWT via MajorLogin
            jwt, account_id, lock_region, server_url = await get_jwt_token(
                client, access_token, open_id
            )
            if not jwt:
                return None

            # Extract nickname from JWT
            nickname = decode_jwt_field(jwt, "nickname", "Unknown")

            token_data = {
                "jwt_token":    jwt,
                "access_token": garena_token,
                "accountId":    account_id or uid,
                "nickname":     nickname,
                "lockRegion":   lock_region,
                "serverUrl":    server_url,
            }

            # Save to file
            save_token_to_file(uid, pwd, token_data)

            return token_data

    except Exception as e:
        log(f"❌ Pipeline error: {e}")
        return None