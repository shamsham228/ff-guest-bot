# stats_manager.py
# Handles all statistics tracking and saving

import json
import os
from datetime import datetime
from threading import Lock

STATS_FILE = "stats.json"
_lock = Lock()

# Default stats structure
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
    "hourly_counts": {},
    "daily_counts": {}
}


def load_stats() -> dict:
    """Load stats from file"""
    if not os.path.exists(STATS_FILE):
        stats = DEFAULT_STATS.copy()
        stats["start_time"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        save_stats(stats)
        return stats

    with _lock:
        try:
            with open(STATS_FILE, "r") as f:
                return json.load(f)
        except Exception:
            return DEFAULT_STATS.copy()


def save_stats(stats: dict) -> None:
    """Save stats to file"""
    with _lock:
        try:
            with open(STATS_FILE, "w") as f:
                json.dump(stats, f, indent=4)
        except Exception as e:
            print(f"[Stats] Save error: {e}")


def record_success(uid: str, token_generated: bool) -> None:
    """Record a successful account creation"""
    stats = load_stats()

    stats["total_created"] += 1
    stats["total_success"] += 1
    stats["last_created"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    if token_generated:
        stats["total_tokens"] += 1

    # Add to recent accounts (keep last 20)
    stats["recent_accounts"].insert(0, {
        "uid": uid,
        "time": datetime.now().strftime("%H:%M:%S"),
        "token": token_generated
    })
    stats["recent_accounts"] = stats["recent_accounts"][:20]

    # Hourly count
    hour_key = datetime.now().strftime("%Y-%m-%d %H:00")
    stats["hourly_counts"][hour_key] = stats["hourly_counts"].get(hour_key, 0) + 1

    # Daily count
    day_key = datetime.now().strftime("%Y-%m-%d")
    stats["daily_counts"][day_key] = stats["daily_counts"].get(day_key, 0) + 1

    save_stats(stats)


def record_failure() -> None:
    """Record a failed attempt"""
    stats = load_stats()
    stats["total_created"] += 1
    stats["total_failed"] += 1
    save_stats(stats)


def record_request() -> None:
    """Record a bot request"""
    stats = load_stats()
    stats["total_requests"] += 1
    save_stats(stats)


def record_banned_proxy() -> None:
    """Record a banned proxy"""
    stats = load_stats()
    stats["banned_proxies"] += 1
    save_stats(stats)


def get_success_rate() -> float:
    """Get success rate percentage"""
    stats = load_stats()
    total = stats["total_created"]
    if total == 0:
        return 0.0
    return round((stats["total_success"] / total) * 100, 2)


def get_today_count() -> int:
    """Get today's creation count"""
    stats = load_stats()
    day_key = datetime.now().strftime("%Y-%m-%d")
    return stats["daily_counts"].get(day_key, 0)