# token_generator.py
import json
import base64
import asyncio
import httpx
import os
import random
from datetime import datetime
from Crypto.Cipher import AES
from typing import Dict, Any

# ── Proto import ──────────────────────────────────────────────────
freefire_pb2    = None
PROTO_AVAILABLE = False

try:
    from ff_proto import freefire_pb2
    from google.protobuf import json_format
    PROTO_AVAILABLE = True
    print("[Token] ✅ Protobuf loaded")
except Exception as e:
    PROTO_AVAILABLE = False
    print(f"[Token] ⚠️ Protobuf unavailable: {e}")

TOKEN_FILE    = "accounts_with_tokens.json"
MAIN_KEY      = base64.b64decode("WWcmdGMlREV1aDYlWmNeOA==")
MAIN_IV       = base64.b64decode("Nm95WkRyMjJFM3ljaGpNJQ==")
OAUTH_URL     = "https://ffmconnect.live.gop.garenanow.com/api/v2/oauth/guest/token:grant"
MAJOR_URL     = "https://loginbp.ggwhitehawk.com/MajorLogin"
CLIENT_ID     = 100067
CLIENT_SECRET = "2ee44819e9b4598845141067b281621874d0d5d7af9d8f7e00c1e54715b7d1e3"

DALVIK_UAS = [
    "Dalvik/2.1.0 (Linux; U; Android 14; SM-A546B Build/UP1A.231005.007)",
    "Dalvik/2.1.0 (Linux; U; Android 13; 2201116SG Build/TKQ1.220829.002)",
    "Dalvik/2.1.0 (Linux; U; Android 13; NE2210 Build/RKQ1.211119.001)",
    "Dalvik/2.1.0 (Linux; U; Android 13; RMX3706 Build/TP1A.220624.014)",
]


def _pad(data: bytes) -> bytes:
    n = 16 - len(data) % 16
    return data + bytes([n] * n)


def _aes_encrypt(data: bytes) -> bytes:
    return AES.new(MAIN_KEY, AES.MODE_CBC, MAIN_IV).encrypt(_pad(data))


def _decode_jwt(token: str, field: str, default=None):
    try:
        part = token.split('.')[1]
        part += '=' * (-len(part) % 4)
        decoded = base64.urlsafe_b64decode(part)
        return json.loads(decoded).get(field, default)
    except Exception:
        return default


def _save_token(uid: str, pwd: str, td: dict) -> None:
    try:
        tokens: dict = {}
        if os.path.exists(TOKEN_FILE):
            try:
                with open(TOKEN_FILE) as f:
                    tokens = json.load(f)
            except Exception:
                tokens = {}

        # Deduplicate
        for e in tokens.values():
            if e.get("uid") == uid:
                return

        ct  = int(datetime.now().timestamp())
        idx = len(tokens) + 1
        tokens[f"token_{idx}"] = {
            "uid":           uid,
            "password":      pwd,
            "account_id":    td.get("accountId", uid),
            "nickname":      td.get("nickname", ""),
            "agora_env":     "live",
            "create_time":   ct,
            "expiry_time":   ct + 1_296_000,
            "ip_region":     "IN",
            "lock_region":   td.get("lockRegion", "IND"),
            "noti_region":   td.get("lockRegion", "IND"),
            "platform":      4,
            "scope":         ["get_user_info","get_friends","payment","send_request"],
            "server":        td.get("serverUrl", "https://client.ind.freefiremobile.com"),
            "ttl":           28800,
            "jwt_token":     td.get("jwt_token", ""),
            "access_token":  td.get("access_token", ""),
            "status":        "✅ ACTIVE",
        }

        with open(TOKEN_FILE, "w") as f:
            json.dump(tokens, f, indent=4)

        print(f"[Token] 💾 Saved token_{idx}")

    except Exception as e:
        print(f"[Token] ❌ Save error: {e}")


async def process_uid_pwd_with_token(uid: str, pwd: str) -> Dict[str, Any] | None:
    """Generate JWT token for a guest account"""
    if not PROTO_AVAILABLE:
        print("[Token] ⚠️ Skipping token — protobuf not available")
        return None

    try:
        async with httpx.AsyncClient(
            timeout=20.0,
            follow_redirects=True,
            verify=False
        ) as client:

            # Step 1: OAuth
            r1 = await client.post(
                OAUTH_URL,
                json={
                    "client_id":     CLIENT_ID,
                    "client_secret": CLIENT_SECRET,
                    "client_type":   2,
                    "password":      pwd,
                    "response_type": "token",
                    "uid":           int(uid),
                },
                headers={
                    "User-Agent":   "GarenaMSDK/4.0.19P10",
                    "Content-Type": "application/json; charset=utf-8",
                    "Accept":       "application/json",
                }
            )

            d1           = r1.json().get("data", {})
            access_token = d1.get("access_token", "")
            open_id      = d1.get("open_id", "")

            if not access_token:
                print(f"[Token] ❌ No access_token: {r1.text[:200]}")
                return None

            # Step 2: Build protobuf LoginReq
            req = freefire_pb2.LoginReq()
            json_format.ParseDict({
                "open_id":             open_id,
                "open_id_type":        "4",
                "login_token":         access_token,
                "orign_platform_type": "4",
            }, req)

            encrypted = _aes_encrypt(req.SerializeToString())

            # Step 3: MajorLogin
            r2 = await client.post(
                MAJOR_URL,
                content=encrypted,
                headers={
                    "User-Agent":      random.choice(DALVIK_UAS),
                    "Content-Type":    "application/octet-stream",
                    "Accept-Encoding": "gzip",
                    "X-Unity-Version": "2018.4.11f1",
                    "ReleaseVersion":  "OB53",
                    "X-GA":            "v1 1",
                }
            )

            # Step 4: Decode LoginRes
            res = freefire_pb2.LoginRes()
            res.ParseFromString(r2.content)

            jwt = res.token or ""
            if not jwt:
                print("[Token] ❌ Empty JWT from MajorLogin")
                return None

            nick = _decode_jwt(jwt, "nickname", "")
            td = {
                "jwt_token":    jwt,
                "access_token": access_token,
                "accountId":    str(res.account_id) if res.account_id else uid,
                "nickname":     nick,
                "lockRegion":   res.lock_region or "IND",
                "serverUrl":    res.server_url or "https://client.ind.freefiremobile.com",
            }

            _save_token(uid, pwd, td)
            print(f"[Token] ✅ JWT OK — Account: {td['accountId']}")
            return td

    except Exception as e:
        print(f"[Token] ❌ Error: {e}")
        return None
