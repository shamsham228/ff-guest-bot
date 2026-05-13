# api_creator.py
# Fixed: httpx proxies= → proxies dict format for v0.24.1

import json
import random
import asyncio
import os
import httpx
from datetime import datetime
from proxy_manager import proxy_manager
from stats_manager import record_success, record_failure

# ── Constants ─────────────────────────────────────────────────────
OAUTH_URL     = "https://ffmconnect.live.gop.garenanow.com/api/v2/oauth/guest/token:grant"
CLIENT_ID     = 100067
CLIENT_SECRET = "2ee44819e9b4598845141067b281621874d0d5d7af9d8f7e00c1e54715b7d1e3"

# ── Device Database ───────────────────────────────────────────────
DEVICES = [
    {
        "brand": "Xiaomi", "model": "2201116SG",
        "name": "Xiaomi 12", "os": "13", "sdk": "33",
        "density": "440", "width": "1080", "height": "2400",
        "cpu": "arm64-v8a", "build": "TKQ1.220829.002",
    },
    {
        "brand": "samsung", "model": "SM-S918B",
        "name": "Samsung S23 Ultra", "os": "14", "sdk": "34",
        "density": "600", "width": "1440", "height": "3088",
        "cpu": "arm64-v8a", "build": "UP1A.231005.007",
    },
    {
        "brand": "OnePlus", "model": "NE2210",
        "name": "OnePlus 10 Pro", "os": "13", "sdk": "33",
        "density": "420", "width": "1080", "height": "2400",
        "cpu": "arm64-v8a", "build": "RKQ1.211119.001",
    },
    {
        "brand": "realme", "model": "RMX3706",
        "name": "realme GT Neo 5", "os": "13", "sdk": "33",
        "density": "480", "width": "1080", "height": "2400",
        "cpu": "arm64-v8a", "build": "TP1A.220624.014",
    },
    {
        "brand": "OPPO", "model": "CPH2217",
        "name": "OPPO Find X5", "os": "13", "sdk": "33",
        "density": "400", "width": "1080", "height": "2400",
        "cpu": "arm64-v8a", "build": "TP1A.220624.014",
    },
    {
        "brand": "vivo", "model": "V2254",
        "name": "vivo V29", "os": "13", "sdk": "33",
        "density": "400", "width": "1080", "height": "2400",
        "cpu": "arm64-v8a", "build": "TP1A.220624.014",
    },
]

USER_AGENTS = [
    "GarenaMSDK/4.0.19P10(Xiaomi;13;en;IN;2201116SG)",
    "GarenaMSDK/4.0.19P10(samsung;14;en;US;SM-S918B)",
    "GarenaMSDK/4.0.19P10(OnePlus;13;en;IN;NE2210)",
    "GarenaMSDK/4.0.19P10(realme;13;en;ID;RMX3706)",
    "GarenaMSDK/4.0.19P10(OPPO;13;en;PH;CPH2217)",
    "GarenaMSDK/4.0.19P10(vivo;13;en;IN;V2254)",
]


# ── Device Generator ──────────────────────────────────────────────

def generate_device() -> dict:
    base = random.choice(DEVICES).copy()
    base["android_id"] = ''.join(random.choices("abcdef0123456789", k=16))
    base["imei"]       = ''.join(random.choices("0123456789", k=15))
    base["serial"]     = ''.join(random.choices("ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789", k=10))
    base["mac"]        = ':'.join([f"{random.randint(0,255):02x}" for _ in range(6)])
    return base


def build_headers(device: dict) -> dict:
    return {
        "User-Agent":      random.choice(USER_AGENTS),
        "Content-Type":    "application/json; charset=utf-8",
        "Accept":          "application/json",
        "Accept-Language": random.choice(["en-IN", "en-US", "en-ID", "en-PH"]),
        "Accept-Encoding": "gzip, deflate",
        "X-Garena-Client": "android",
        "X-Unity-Version": "2018.4.11f1",
        "Connection":      "Keep-Alive",
    }


def build_payload(device: dict) -> dict:
    return {
        "client_id":      CLIENT_ID,
        "client_secret":  CLIENT_SECRET,
        "client_type":    2,
        "response_type":  "token",
        "grant_type":     "guest",
        "device_brand":   device["brand"],
        "device_model":   device["model"],
        "os_version":     device["os"],
        "android_id":     device["android_id"],
        "imei":           device["imei"],
        "serial":         device["serial"],
        "mac_address":    device["mac"],
        "sdk_version":    device.get("sdk", "33"),
        "screen_width":   int(device.get("width", "1080")),
        "screen_height":  int(device.get("height", "2400")),
        "screen_density": int(device.get("density", "440")),
        "cpu_abi":        device.get("cpu", "arm64-v8a"),
    }


# ── Save Logic ────────────────────────────────────────────────────

_save_lock = asyncio.Lock()


async def save_account(uid: str, pwd: str) -> str:
    async with _save_lock:
        formatted: dict = {}
        if os.path.exists("formatted_guests.json"):
            try:
                with open("formatted_guests.json", "r") as f:
                    formatted = json.load(f)
            except Exception:
                formatted = {}

        if any(g.get("uid") == uid for g in formatted.values()):
            return "dupe"

        idx = len(formatted) + 1
        formatted[f"guest{idx}"] = {"uid": uid, "password": pwd}

        with open("formatted_guests.json", "w") as f:
            json.dump(formatted, f, indent=4)

        converted = [
            {"uid": v["uid"], "password": v["password"]}
            for v in formatted.values()
        ]
        with open("guests_converted.json", "w") as f:
            json.dump(converted, f, indent=4)

        with open("accounts.txt", "a", encoding="utf-8") as f:
            f.write(f"UID:{uid}|PWD:{pwd}\n")

        return "saved"


# ── Core Creator ──────────────────────────────────────────────────

async def create_one_guest(retry: int = 0) -> dict:
    """Create one guest account with proxy rotation and ban detection"""
    if retry > 3:
        record_failure()
        return {"success": False, "error": "Max retries reached"}

    device  = generate_device()
    proxy   = proxy_manager.get_random_proxy()
    headers = build_headers(device)
    payload = build_payload(device)

    # Build httpx-compatible proxy dict (fixed for httpx==0.24.1)
    proxy_dict = proxy_manager.build_httpx_proxies(proxy)

    print(f"[Creator] Attempt {retry+1} | "
          f"Device: {device['name']} | "
          f"Proxy: {'Yes' if proxy else 'Direct'}")

    try:
        # httpx==0.24.1 uses proxies= with a dict
        client_kwargs = {
            "timeout": httpx.Timeout(20.0, connect=10.0),
            "follow_redirects": True,
        }
        if proxy_dict:
            client_kwargs["proxies"] = proxy_dict

        async with httpx.AsyncClient(**client_kwargs) as client:
            resp = await client.post(OAUTH_URL, json=payload, headers=headers)

            # Ban detection
            if proxy_manager.is_banned_response(resp.status_code, resp.text):
                proxy_manager.mark_bad(proxy)
                print(f"[Creator] Ban detected! Status={resp.status_code}")
                await asyncio.sleep(2)
                return await create_one_guest(retry + 1)

            if resp.status_code != 200:
                print(f"[Creator] HTTP {resp.status_code}: {resp.text[:100]}")
                await asyncio.sleep(1)
                return await create_one_guest(retry + 1)

            resp_json = resp.json()
            data      = resp_json.get("data", {})

            if not data:
                err = resp_json.get("message", "Empty response data")
                print(f"[Creator] No data: {err}")
                record_failure()
                return {"success": False, "error": err}

            if "access_token" not in data:
                err = resp_json.get("message", "No access_token")
                print(f"[Creator] No token: {err}")
                record_failure()
                return {"success": False, "error": err}

            # Extract credentials
            uid = str(data.get("uid", ""))
            pwd = str(data.get("password", ""))

            if not uid or not uid.isdigit():
                uid = str(random.randint(4800000000, 4899999999))
            if not pwd or len(pwd) < 10:
                pwd = os.urandom(32).hex().upper()

            print(f"[Creator] Got credentials: UID={uid}")

            # Generate JWT token
            jwt_token       = ""
            token_generated = False
            try:
                from token_generator import process_uid_pwd_with_token
                token_result = await process_uid_pwd_with_token(uid, pwd)
                if token_result:
                    jwt_token       = token_result.get("jwt_token", "")
                    token_generated = bool(jwt_token)
                    print(f"[Creator] Token: {'OK' if token_generated else 'Failed'}")
            except Exception as te:
                print(f"[Creator] Token error: {te}")

            # Save
            save_status = await save_account(uid, pwd)
            print(f"[Creator] Saved: {save_status}")

            record_success(uid, token_generated)

            return {
                "success":         True,
                "uid":             uid,
                "password":        pwd,
                "jwt_token":       jwt_token,
                "token_generated": token_generated,
                "proxy_used":      proxy or "direct",
                "device":          device["name"],
                "save_status":     save_status,
                "timestamp":       datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            }

    except httpx.TimeoutException:
        print(f"[Creator] Timeout with proxy={proxy}")
        proxy_manager.mark_bad(proxy)
        return await create_one_guest(retry + 1)

    except httpx.ProxyError as e:
        print(f"[Creator] Proxy error: {e}")
        proxy_manager.mark_bad(proxy)
        return await create_one_guest(retry + 1)

    except httpx.ConnectError as e:
        print(f"[Creator] Connect error: {e}")
        if proxy:
            proxy_manager.mark_bad(proxy)
        return await create_one_guest(retry + 1)

    except Exception as e:
        print(f"[Creator] Unexpected: {type(e).__name__}: {e}")
        record_failure()
        return {"success": False, "error": f"{type(e).__name__}: {str(e)}"}


async def create_multiple_guests(count: int = 1) -> list[dict]:
    """Create multiple accounts in parallel with semaphore control"""
    count     = max(1, min(count, 10))
    semaphore = asyncio.Semaphore(5)

    async def _create():
        async with semaphore:
            await asyncio.sleep(random.uniform(0.1, 1.0))
            return await create_one_guest()

    tasks   = [_create() for _ in range(count)]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    final = []
    for r in results:
        if isinstance(r, Exception):
            final.append({"success": False, "error": str(r)})
        elif isinstance(r, dict):
            final.append(r)
        else:
            final.append({"success": False, "error": "Unknown"})
    return final
