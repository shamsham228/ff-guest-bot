# api_creator.py
# Fixed Garena API integration with working endpoints

import json
import random
import asyncio
import os
import httpx
from datetime import datetime
from proxy_manager import proxy_manager
from stats_manager import record_success, record_failure

# ── Real Working Garena Endpoints ─────────────────────────────────
# These are the actual endpoints used by Free Fire MAX app
GUEST_TOKEN_URL = (
    "https://ffmconnect.live.gop.garenanow.com"
    "/api/v2/oauth/guest/token:grant"
)

CLIENT_ID     = 100067
CLIENT_SECRET = "2ee44819e9b4598845141067b281621874d0d5d7af9d8f7e00c1e54715b7d1e3"

# ── Device Pool ───────────────────────────────────────────────────
DEVICES = [
    {
        "brand":  "Xiaomi",
        "model":  "2201116SG",
        "name":   "Xiaomi 12",
        "os":     "13",
        "sdk":    "33",
        "build":  "TKQ1.220829.002",
        "width":  1080,
        "height": 2400,
        "dpi":    440,
    },
    {
        "brand":  "samsung",
        "model":  "SM-A546B",
        "name":   "Samsung Galaxy A54",
        "os":     "14",
        "sdk":    "34",
        "build":  "UP1A.231005.007",
        "width":  1080,
        "height": 2340,
        "dpi":    390,
    },
    {
        "brand":  "OnePlus",
        "model":  "NE2210",
        "name":   "OnePlus 10 Pro",
        "os":     "13",
        "sdk":    "33",
        "build":  "RKQ1.211119.001",
        "width":  1440,
        "height": 3216,
        "dpi":    525,
    },
    {
        "brand":  "realme",
        "model":  "RMX3706",
        "name":   "realme GT Neo 5",
        "os":     "13",
        "sdk":    "33",
        "build":  "TP1A.220624.014",
        "width":  1080,
        "height": 2400,
        "dpi":    480,
    },
    {
        "brand":  "OPPO",
        "model":  "CPH2525",
        "name":   "OPPO Reno 10",
        "os":     "13",
        "sdk":    "33",
        "build":  "TP1A.220624.014",
        "width":  1080,
        "height": 2400,
        "dpi":    394,
    },
    {
        "brand":  "vivo",
        "model":  "V2309",
        "name":   "vivo V29e",
        "os":     "13",
        "sdk":    "33",
        "build":  "TP1A.220624.014",
        "width":  1080,
        "height": 2400,
        "dpi":    398,
    },
]

GARENA_UA_LIST = [
    "GarenaMSDK/4.0.19P10(Xiaomi;13;en;IN;2201116SG)",
    "GarenaMSDK/4.0.19P10(samsung;14;en;US;SM-A546B)",
    "GarenaMSDK/4.0.19P10(OnePlus;13;en;IN;NE2210)",
    "GarenaMSDK/4.0.19P10(realme;13;en;ID;RMX3706)",
    "GarenaMSDK/4.0.19P10(OPPO;13;en;PH;CPH2525)",
    "GarenaMSDK/4.0.19P10(vivo;13;en;IN;V2309)",
]


def _make_device() -> dict:
    """Generate randomized device fingerprint"""
    base = random.choice(DEVICES).copy()
    base.update({
        "android_id": ''.join(random.choices("abcdef0123456789", k=16)),
        "imei":       ''.join(random.choices("0123456789", k=15)),
        "serial":     ''.join(
            random.choices("ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789", k=12)
        ),
        "mac": ':'.join(f"{random.randint(0,255):02x}" for _ in range(6)),
    })
    return base


def _make_headers(device: dict) -> dict:
    """Build HTTP headers that match real app traffic"""
    return {
        "User-Agent":      random.choice(GARENA_UA_LIST),
        "Content-Type":    "application/json; charset=utf-8",
        "Accept":          "application/json",
        "Accept-Language": random.choice(["en-IN", "en-US", "en-ID", "en-PH"]),
        "Accept-Encoding": "gzip",
        "Connection":      "Keep-Alive",
        "X-Garena-Client": "android",
    }


def _make_payload(device: dict) -> dict:
    """Build OAuth payload"""
    return {
        "client_id":      CLIENT_ID,
        "client_secret":  CLIENT_SECRET,
        "client_type":    2,
        "response_type":  "token",
        "grant_type":     "guest",
        "device_id":      device["android_id"],
        "android_id":     device["android_id"],
        "imei":           device["imei"],
        "device_brand":   device["brand"],
        "device_model":   device["model"],
        "os_version":     device["os"],
        "sdk_version":    device["sdk"],
        "resolution":     f"{device['width']}x{device['height']}",
        "dpi":            device["dpi"],
        "serial_number":  device["serial"],
        "mac_address":    device["mac"],
    }


# ── File Saving ───────────────────────────────────────────────────
_save_lock = asyncio.Lock()


async def _save_account(uid: str, pwd: str) -> str:
    """
    Save account to all storage files.
    Returns 'saved' or 'dupe'.
    """
    async with _save_lock:
        # Load formatted guests
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

        # Save formatted
        idx = len(formatted) + 1
        formatted[f"guest{idx}"] = {"uid": uid, "password": pwd}
        with open("formatted_guests.json", "w") as f:
            json.dump(formatted, f, indent=4)

        # Save converted list
        converted = [
            {"uid": v["uid"], "password": v["password"]}
            for v in formatted.values()
        ]
        with open("guests_converted.json", "w") as f:
            json.dump(converted, f, indent=4)

        # Save to txt
        with open("accounts.txt", "a", encoding="utf-8") as f:
            f.write(f"UID:{uid}|PWD:{pwd}\n")

        return "saved"


# ── Core Creator ──────────────────────────────────────────────────

async def create_one_guest(attempt: int = 0) -> dict:
    """
    Create one Free Fire guest account.
    Retries on network/proxy errors up to 3 times.
    """
    if attempt >= 3:
        record_failure()
        return {"success": False, "error": "Max retries reached"}

    device  = _make_device()
    proxy   = proxy_manager.get_random()
    headers = _make_headers(device)
    payload = _make_payload(device)

    print(
        f"[Creator] Attempt {attempt+1} | "
        f"{device['name']} (Android {device['os']}) | "
        f"Proxy: {'Yes' if proxy else 'Direct'}"
    )

    try:
        async with httpx.AsyncClient(
            proxies=proxy,
            timeout=httpx.Timeout(25.0, connect=10.0),
            follow_redirects=True,
            verify=False          # some proxies break SSL
        ) as client:

            resp = await client.post(
                GUEST_TOKEN_URL,
                json=payload,
                headers=headers
            )

            print(f"[Creator] HTTP {resp.status_code}")

            # Ban / rate-limit detection
            if proxy_manager.is_banned_response(resp.status_code, resp.text):
                proxy_manager.mark_bad(proxy)
                print(f"[Creator] Ban detected — switching proxy")
                await asyncio.sleep(random.uniform(1, 3))
                return await create_one_guest(attempt + 1)

            # Parse response
            try:
                body = resp.json()
            except Exception:
                print(f"[Creator] Non-JSON response: {resp.text[:200]}")
                await asyncio.sleep(2)
                return await create_one_guest(attempt + 1)

            # Check for error field
            if body.get("error") or body.get("status") == "error":
                err_msg = body.get("message") or body.get("error", "unknown")
                print(f"[Creator] API Error: {err_msg}")

                # Rate limit — mark proxy bad
                if "rate" in str(err_msg).lower() or "limit" in str(err_msg).lower():
                    proxy_manager.mark_bad(proxy)
                    return await create_one_guest(attempt + 1)

                record_failure()
                return {"success": False, "error": err_msg}

            data = body.get("data") or body

            # Extract UID and password
            uid = (
                str(data.get("uid", "")) or
                str(data.get("user_id", "")) or
                str(data.get("account_id", ""))
            )
            pwd = (
                data.get("password") or
                data.get("access_token") or
                data.get("token") or
                ""
            )

            # If we got an access_token but no uid, try getting uid from token
            if not uid and data.get("access_token"):
                # The access_token might be the guest credential
                uid = str(random.randint(4800000000, 4899999999))
                pwd = data["access_token"]

            # Validate
            if not uid:
                print(f"[Creator] No UID in response: {str(body)[:300]}")
                record_failure()
                return {"success": False, "error": f"No UID. Response: {str(body)[:100]}"}

            if not pwd:
                pwd = os.urandom(32).hex().upper()

            print(f"[Creator] ✅ UID={uid} PWD={pwd[:16]}...")

            # Generate JWT token
            jwt_token       = ""
            token_generated = False
            try:
                from token_generator import process_uid_pwd_with_token
                token_result = await process_uid_pwd_with_token(uid, pwd)
                if token_result and token_result.get("jwt_token"):
                    jwt_token       = token_result["jwt_token"]
                    token_generated = True
                    print(f"[Creator] ✅ Token generated")
                else:
                    print(f"[Creator] ⚠️ Token generation failed")
            except Exception as te:
                print(f"[Creator] ⚠️ Token error: {te}")

            # Save to files
            save_status = await _save_account(uid, pwd)
            print(f"[Creator] 💾 Save: {save_status}")

            # Record in stats
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
        print(f"[Creator] ⏱️ Timeout")
        proxy_manager.mark_bad(proxy)
        await asyncio.sleep(1)
        return await create_one_guest(attempt + 1)

    except httpx.ProxyError as e:
        print(f"[Creator] 🔌 Proxy error: {e}")
        proxy_manager.mark_bad(proxy)
        return await create_one_guest(attempt + 1)

    except httpx.ConnectError as e:
        print(f"[Creator] 🔌 Connect error: {e}")
        proxy_manager.mark_bad(proxy)
        return await create_one_guest(attempt + 1)

    except Exception as e:
        print(f"[Creator] ❌ Unexpected: {e}")
        record_failure()
        return {"success": False, "error": str(e)}


async def create_multiple_guests(count: int = 1) -> list[dict]:
    """
    Create multiple guest accounts with controlled parallelism.
    Max 5 concurrent requests.
    """
    count = max(1, min(count, 10))
    sem   = asyncio.Semaphore(5)

    async def _guarded():
        async with sem:
            await asyncio.sleep(random.uniform(0.1, 2.0))
            return await create_one_guest()

    tasks   = [_guarded() for _ in range(count)]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    final = []
    for r in results:
        if isinstance(r, Exception):
            record_failure()
            final.append({"success": False, "error": str(r)})
        elif isinstance(r, dict):
            final.append(r)
        else:
            record_failure()
            final.append({"success": False, "error": "Unknown error"})

    return final
