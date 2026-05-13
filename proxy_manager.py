# proxy_manager.py
# Handles proxy rotation, testing, and ban detection

import asyncio
import httpx
import random
from datetime import datetime, timedelta
from stats_manager import record_banned_proxy

# ── Ban Detection Patterns ────────────────────────────────────────
BAN_STATUS_CODES = {403, 429, 503, 407, 401}
BAN_KEYWORDS     = [
    "banned", "blocked", "rate limit", "too many",
    "captcha", "forbidden", "access denied", "ip blocked"
]

# ── Proxy Pool ────────────────────────────────────────────────────
class ProxyManager:
    def __init__(self, proxy_file: str = "proxies.txt"):
        self.proxies: list[str]        = []
        self.bad_proxies: set[str]     = set()
        self.proxy_errors: dict        = {}
        self.last_used_index: int      = 0
        self.use_proxies: bool         = False
        self._load_proxies(proxy_file)

    def _load_proxies(self, proxy_file: str) -> None:
        """Load proxies from file"""
        try:
            with open(proxy_file, "r") as f:
                lines = f.readlines()

            self.proxies = [
                line.strip()
                for line in lines
                if line.strip() and not line.strip().startswith("#")
            ]

            if self.proxies:
                self.use_proxies = True
                print(f"[Proxy] Loaded {len(self.proxies)} proxies")
            else:
                print("[Proxy] No proxies found — using direct connection")

        except FileNotFoundError:
            print("[Proxy] proxies.txt not found — using direct connection")
            self.proxies = []

    def get_proxy(self) -> str | None:
        """Get next available proxy using round-robin"""
        if not self.use_proxies or not self.proxies:
            return None

        # Filter out bad proxies
        available = [p for p in self.proxies if p not in self.bad_proxies]

        if not available:
            # Reset bad proxies and try again
            print("[Proxy] All proxies bad — resetting bad proxy list")
            self.bad_proxies.clear()
            available = self.proxies

        # Round-robin selection
        proxy = available[self.last_used_index % len(available)]
        self.last_used_index += 1
        return proxy

    def get_random_proxy(self) -> str | None:
        """Get a random available proxy"""
        if not self.use_proxies or not self.proxies:
            return None

        available = [p for p in self.proxies if p not in self.bad_proxies]
        if not available:
            self.bad_proxies.clear()
            available = self.proxies

        return random.choice(available) if available else None

    def mark_bad(self, proxy: str | None) -> None:
        """Mark proxy as bad/banned"""
        if proxy:
            self.bad_proxies.add(proxy)
            self.proxy_errors[proxy] = self.proxy_errors.get(proxy, 0) + 1
            record_banned_proxy()
            print(f"[Proxy] 🚫 Marked bad: {proxy[:30]}...")

    def is_banned_response(self, status_code: int, content: str = "") -> bool:
        """Check if response indicates ban/block"""
        if status_code in BAN_STATUS_CODES:
            return True

        content_lower = content.lower()
        for keyword in BAN_KEYWORDS:
            if keyword in content_lower:
                return True

        return False

    def get_stats(self) -> dict:
        """Get proxy statistics"""
        return {
            "total_proxies": len(self.proxies),
            "bad_proxies": len(self.bad_proxies),
            "available_proxies": len(self.proxies) - len(self.bad_proxies),
            "using_proxies": self.use_proxies
        }

    async def test_proxy(self, proxy: str) -> bool:
        """Test if a proxy works"""
        try:
            async with httpx.AsyncClient(proxies=proxy, timeout=10) as client:
                resp = await client.get("https://httpbin.org/ip")
                return resp.status_code == 200
        except Exception:
            return False

    async def scrape_free_proxies(self) -> list[str]:
        """
        Auto-scrape free proxies from public lists.
        This runs automatically if proxy list runs low.
        """
        scraped = []
        sources = [
            "https://raw.githubusercontent.com/TheSpeedX/PROXY-List/master/http.txt",
            "https://raw.githubusercontent.com/clarketm/proxy-list/master/proxy-list-raw.txt",
            "https://raw.githubusercontent.com/ShiftyTR/Proxy-List/master/http.txt",
        ]

        async with httpx.AsyncClient(timeout=15) as client:
            for source in sources:
                try:
                    resp = await client.get(source)
                    if resp.status_code == 200:
                        lines = resp.text.strip().split('\n')
                        for line in lines[:50]:  # Take first 50 from each source
                            line = line.strip()
                            if ':' in line and line:
                                proxy = f"http://{line}" if not line.startswith("http") else line
                                scraped.append(proxy)
                except Exception:
                    continue

        # Add scraped proxies to pool
        new_proxies = [p for p in scraped if p not in self.proxies]
        self.proxies.extend(new_proxies)

        # Save to file
        if new_proxies:
            with open("proxies.txt", "a") as f:
                for p in new_proxies:
                    f.write(f"\n{p}")
            print(f"[Proxy] 🔄 Scraped {len(new_proxies)} new proxies")

        return new_proxies


# ── Global Proxy Manager Instance ────────────────────────────────
proxy_manager = ProxyManager()