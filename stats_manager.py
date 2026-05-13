# stats_manager.py
import json
import os
from datetime import datetime
from threading import Lock

STATS_FILE = "stats.json"
_lock = Lock()

DEFAULT_STATS = {
    "total_created": 0,
    "total_success": 0,
    "total_failed": 0,
    "total_tokens": 0,
    "total_requests": 0,
    "banned_proxies": 0,
    "start_time": "",
    "last_created": "",
    "recent_accounts": [],
    "daily_counts": {}
}


def load_stats() -> dict:
    if not os.path.exists(STATS_FILE):
        s = DEFAULT_STATS.copy()
        s["start_time"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        save_stats(s)
        return s
    with _lock:
        try:
            with open(STATS_FILE, "r") as f:
                data = json.load(f)
                # Make sure all keys exist
                for k, v in DEFAULT_STATS.items():
                    if k not in data:
                        data[k] = v
                return data
        except Exception:
            s = DEFAULT_STATS.copy()
            s["start_time"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            return s


def save_stats(stats: dict) -> None:
    with _lock:
        try:
            with open(STATS_FILE, "w") as f:
                json.dump(stats, f, indent=4)
        except Exception as e:
            print(f"[Stats] Save error: {e}")


def record_success(uid: str, token_generated: bool) -> None:
    stats = load_stats()
    stats["total_created"] += 1
    stats["total_success"] += 1
    stats["last_created"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    if token_generated:
        stats["total_tokens"] += 1
    stats["recent_accounts"].insert(0, {
        "uid": uid,
        "time": datetime.now().strftime("%H:%M:%S"),
        "token": token_generated
    })
    stats["recent_accounts"] = stats["recent_accounts"][:20]
    day_key = datetime.now().strftime("%Y-%m-%d")
    stats["daily_counts"][day_key] = stats["daily_counts"].get(day_key, 0) + 1
    save_stats(stats)


def record_failure() -> None:
    stats = load_stats()
    stats["total_created"] += 1
    stats["total_failed"] += 1
    save_stats(stats)


def record_request() -> None:
    stats = load_stats()
    stats["total_requests"] += 1
    save_stats(stats)


def record_banned_proxy() -> None:
    stats = load_stats()
    stats["banned_proxies"] += 1
    save_stats(stats)


def get_success_rate() -> float:
    stats = load_stats()
    total = stats["total_created"]
    if total == 0:
        return 0.0
    return round((stats["total_success"] / total) * 100, 2)


def get_today_count() -> int:
    stats = load_stats()
    day_key = datetime.now().strftime("%Y-%m-%d")
    return stats["daily_counts"].get(day_key, 0)


def get_total_accounts() -> int:
    try:
        with open("guests_converted.json", "r") as f:
            return len(json.load(f))
    except Exception:
        return 0


def get_uptime() -> str:
    try:
        stats = load_stats()
        start = datetime.strptime(stats["start_time"], "%Y-%m-%d %H:%M:%S")
        diff = datetime.now() - start
        hours = int(diff.total_seconds() // 3600)
        mins = int((diff.total_seconds() % 3600) // 60)
        return f"{hours}h {mins}m"
    except Exception:
        return "Unknown"
