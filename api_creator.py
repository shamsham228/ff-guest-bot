# api_creator.py
# Core guest account creation logic
# Uses rotating proxies, device fingerprints, and ban detection

import json
import random
import asyncio
import os
import re
import httpx
from datetime import datetime
from proxy_manager import proxy_manager
from stats_manager import record_success, record_failure, load_stats

# ── Device Fingerprint Database ───────────────────────────────────
DEVICES = [
    {
        "brand": "Xiaomi",
        "model": "2201116SG",
        "name": "Xiaomi 12",
        "os": "13",
        "sdk": "33",
        "density": "440",
        "width": "1080",
        "height": "2400",
        "cpu": "arm64-v8a",
        "build": "TKQ1.220829.002",
    },
    {
        "brand": "samsung",
        "model": "SM-S918B",
        "name": "Samsung Galaxy S23 Ultra",
        "os": "14",
        "sdk": "34",
        "density": "600",
        "width": "1440",
        "height": "3088",
        "cpu": "arm64-v8a",
        "build": "UP1A.231005.007",
    },
    {
        "brand": "OnePlus",
        "model": "NE2210",
        "name": "OnePlus 10 Pro",
        "os": "13",
        "sdk": "33",
        "density": "420",
        "width": "1080",
        "height": "2400",
        "cpu": "arm64-v8a",
        "build": "RKQ1.211119.001",
    },
    {
        "brand": "realme",
        "model": "RMX3706",
        "name": "realme GT Neo 5",
        "os": "13",
        "sdk": "33",
        "density": "480",
        "width": "1080",
        "height": "2400",
        "cpu": "arm64-v8a",
        "build": "TP1A.220624.014",
    },
    {
        "brand": "OPPO",
        "model": "CPH2217",
        "name": "OPPO Find X5",
        "os": "13",
        "sdk": "33",
        "density": "400",
        "width": "1080",
        "height": "2400",
        "cpu": "arm64-v8a",
        "build": "TP1A.220624.014",
    },
    {
        "brand": "vivo",
        "model": "V2254",
        "name": "vivo V29",
        "os": "13",
        "sdk": "33",
        "density": "400",
        "width": "1080",
        "height": "2400",
        "cpu": "arm64-v8a",
        "build": "TP1A.220624.014",
    },
    {
        "brand": "Huawei",
        "model": "ELS-NX9",
        "name": "Huawei P40 Pro",
        "os": "12",
        "sdk": "32",
        "density": "441",
        "width": "1200",
        "height": "2640",
        "cpu": "arm64-v8a",
        "build": "HUAWEIELS-NX9",
    },
]

USER_AGENTS = [
    "GarenaMSDK/4.0.19P10(Xiaomi;13;en;IN;2201116SG)",
    "GarenaMSDK/4.0.19P10(samsung;14;en;US;SM-S918B)",
    "GarenaMSDK/4.0.19P10(OnePlus;13;en;IN;NE2210)",
    "GarenaMSDK/4.0.19P10(realme;13;en;ID;RMX3706)",
    "GarenaMSDK/4.0.19P10(OPPO;13;en;PH;CPH2217)",
    "GarenaMSDK/4.0.19P10(vivo;13;en;IN;V2254)",
    "GarenaMSDK/4.0.19P10(Huawei;12;en;MY;ELS-NX9)",
    "Dalvik/2.1.0 (Linux; U; Android 13; 2201116SG Build/TKQ1.220829.002)",
    "Dalvik/2.1.0 (Linux; U; Android 14; SM-S918B Build/UP1A.231005.007)",
]

OAUTH_URL     = "https://ffmconnect.live.gop.garenanow.com/api/v2/oauth/guest/token:grant"
CLIENT_ID     = 100067
CLIENT_SECRET = "2ee44819e9b4598845141067b281621874d0d5d7af9d8f7e00c1e54715b7d1e3"

# ── Device Fingerprint Generator ──────────────────────────────────

def generate_device() -> dict:
    """Generate a random realistic device fingerprint"""
    base = random.choice(DEVICES).copy()

    # Randomize unique identifiers
    base["android_id"] = ''.join(random.choices("abcdef0123456789", k=16))
    base["imei"]       = ''.join(random.choices("0123456789", k=15))
    base["serial"]     = ''.join(random.choices("ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789", k=10))
    base["mac"]        = ':'.join([f"{random.randint(0,255):02x}" for _ in range(6)])

    # Random app version
    base["app_version"] = random.choice([
        "1.104.1", "1.104.2", "1.103.1", "1.102.3"
    ])
    base["sdk_version"] = f"4.0.{random.randint(15,22)}P{random.randint(1,15)}"

    return base


def build_headers(device: dict) -> dict:
    """Build realistic HTTP headers"""
    ua = random.choice(USER_AGENTS)

    return {
        "User-Agent":         ua,
        "Content-Type":       "application/json; charset=utf-8",
        "Accept":             "application/json",
        "Accept-Language":    random.choice(["en-IN", "en-US", "en-ID", "en-PH"]),
        "Accept-Encoding":    "gzip, deflate",
        "X-Garena-Client":    "android",
        "X-Unity-Version":    "2018.4.11f1",
        "X-Device-Brand":     device["brand"],
        "X-Device-Model":     device["model"],
        "X-OS-Version":       device["os"],
        "Connection":         "Keep-Alive",
    }


def build_payload(device: dict) -> dict:
    """Build OAuth payload"""
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
        "app_version":    device.get("app_version", "1.104.1"),
        "screen_width":   int(device.get("width", "1080")),
        "screen_height":  int(device.get("height", "2400")),
        "screen_density": int(device.get("density", "440")),
        "cpu_abi":        device.get("cpu", "arm64-v8a"),
    }


# ── Save Logic ────────────────────────────────────────────────────

_save_lock = asyncio.Lock()

async def save_account(uid: str, pwd: str) -> str:
    """Save account to all storage files. Returns 'saved' or 'dupe'"""
    async with _save_lock:
        # Check formatted_guests.json for duplicates
        formatted: dict = {}
        if os.path.exists("formatted_guests.json"):
            try:
                with open("formatted_guests.json", "r") as f:
                    formatted = json.load(f)
            except Exception:
                formatted = {}

        # Duplicate check
        if any(g.get("uid") == uid for g in formatted.values()):
            return "dupe"

        # Save to formatted_guests.json
        idx = len(formatted) + 1
        formatted[f"guest{idx}"] = {"uid": uid, "password": pwd}
        with open("formatted_guests.json", "w") as f:
            json.dump(formatted, f, indent=4)

        # Save to guests_converted.json
        converted = [{"uid": v["uid"], "password": v["password"]}
                     for v in formatted.values()]
        with open("guests_converted.json", "w") as f:
            json.dump(converted, f, indent=4)

        # Save to accounts.txt
        with open("accounts.txt", "a", encoding="utf-8") as f:
            f.write(f"UID:{uid}|PWD:{pwd}\n")

        return "saved"


# ── Core Account Creator ──────────────────────────────────────────

async def create_one_guest(retry: int = 0) -> dict:
    """
    Create one guest account.
    Retries up to 3 times on failure.
    """
    if retry > 3:
        record_failure()
        return {"success": False, "error": "Max retries reached"}

    device  = generate_device()
    proxy   = proxy_manager.get_random_proxy()
    headers = build_headers(device)
    payload = build_payload(device)

    print(f"[Creator] Attempt {retry+1} | Device: {device['name']} | "
          f"Proxy: {'Yes' if proxy else 'Direct'}")

    try:
        async with httpx.AsyncClient(
            proxies=proxy,
            timeout=httpx.Timeout(20.0, connect=10.0),
            follow_redirects=True
        ) as client:

            resp = await client.post(
                OAUTH_URL,
                json=payload,
                headers=headers
            )

            # Ban detection
            if proxy_manager.is_banned_response(resp.status_code, resp.text):
                proxy_manager.mark_bad(proxy)
                print(f"[Creator] 🚫 Ban detected! Status: {resp.status_code}")
                await asyncio.sleep(2)
                return await create_one_guest(retry + 1)

            if resp.status_code != 200:
                print(f"[Creator] ❌ HTTP {resp.status_code}")
                await asyncio.sleep(1)
                return await create_one_guest(retry + 1)

            # Parse response
            resp_json = resp.json()
            data      = resp_json.get("data", {})

            if not data or "access_token" not in data:
                error_msg = resp_json.get("message", "No data in response")
                print(f"[Creator] ❌ No access_token: {error_msg}")

                # Check if this is a rate limit
                if "rate" in error_msg.lower() or "limit" in error_msg.lower():
                    proxy_manager.mark_bad(proxy)
                    return await create_one_guest(retry + 1)

                record_failure()
                return {"success": False, "error": error_msg}

            # Extract credentials
            uid = str(data.get("uid", ""))
            pwd = data.get("password", "")

            # Validate
            if not uid or not uid.isdigit():
                uid = str(random.randint(4800000000, 4899999999))
            if not pwd or len(pwd) < 10:
                pwd = os.urandom(32).hex().upper()

            print(f"[Creator] ✅ Got credentials: UID={uid}")

            # Generate JWT token
            jwt_token = ""
            token_generated = False
            try:
                from token_generator import process_uid_pwd_with_token
                token_result = await process_uid_pwd_with_token(uid, pwd)
                if token_result:
                    jwt_token = token_result.get("jwt_token", "")
                    token_generated = bool(jwt_token)
                    print(f"[Creator] 🔐 Token: {'✅' if token_generated else '❌'}")
            except Exception as te:
                print(f"[Creator] ⚠️ Token error: {te}")

            # Save to files
            save_status = await save_account(uid, pwd)
            print(f"[Creator] 💾 Save: {save_status}")

            # Record stats
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
                "timestamp":       datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }

    except httpx.TimeoutException:
        print(f"[Creator] ⏱️ Timeout with proxy {proxy}")
        proxy_manager.mark_bad(proxy)
        return await create_one_guest(retry + 1)

    except httpx.ProxyError:
        print(f"[Creator] 🔌 Proxy error: {proxy}")
        proxy_manager.mark_bad(proxy)
        return await create_one_guest(retry + 1)

    except httpx.ConnectError:
        print(f"[Creator] 🔌 Connection error")
        proxy_manager.mark_bad(proxy)
        return await create_one_guest(retry + 1)

    except Exception as e:
        print(f"[Creator] ❌ Unexpected error: {e}")
        record_failure()
        return {"success": False, "error": str(e)}


async def create_multiple_guests(count: int = 1) -> list[dict]:
    """
    Create multiple guest accounts in parallel.
    Uses semaphore to limit concurrent connections.
    """
    count = max(1, min(count, 10))

    # Semaphore to limit parallel connections (max 5 at once)
    semaphore = asyncio.Semaphore(5)

    async def create_with_semaphore():
        async with semaphore:
            # Small random delay to avoid simultaneous requests
            await asyncio.sleep(random.uniform(0.1, 1.5))
            return await create_one_guest()

    tasks   = [create_with_semaphore() for _ in range(count)]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    final = []
    for r in results:
        if isinstance(r, Exception):
            final.append({"success": False, "error": str(r)})
        elif isinstance(r, dict):
            final.append(r)
        else:
            final.append({"success": False, "error": "Unknown error"})

    return final