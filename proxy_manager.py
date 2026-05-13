# proxy_manager.py
import asyncio
import httpx
import random
from stats_manager import record_banned_proxy

BAN_STATUS_CODES = {403, 429, 503, 407}
BAN_KEYWORDS = [
    "banned", "blocked", "rate limit", "too many",
    "captcha", "forbidden", "access denied"
]


class ProxyManager:
    def __init__(self, proxy_file: str = "proxies.txt"):
        self.proxies: list[str] = []
        self.bad_proxies: set[str] = set()
        self.last_used_index: int = 0
        self.use_proxies: bool = False
        self._load_proxies(proxy_file)

    def _load_proxies(self, proxy_file: str) -> None:
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
                print("[Proxy] No proxies — using direct connection")
        except FileNotFoundError:
            print("[Proxy] proxies.txt not found — direct connection")
            self.proxies = []

    def get_proxy(self) -> str | None:
        """Get next proxy — returns None if no proxies configured"""
        if not self.use_proxies or not self.proxies:
            return None
        available = [p for p in self.proxies if p not in self.bad_proxies]
        if not available:
            print("[Proxy] All proxies bad — resetting")
            self.bad_proxies.clear()
            available = self.proxies
        proxy = available[self.last_used_index % len(available)]
        self.last_used_index += 1
        return proxy

    def get_random_proxy(self) -> str | None:
        """Get random proxy"""
        if not self.use_proxies or not self.proxies:
            return None
        available = [p for p in self.proxies if p not in self.bad_proxies]
        if not available:
            self.bad_proxies.clear()
            available = self.proxies
        return random.choice(available) if available else None

    def mark_bad(self, proxy: str | None) -> None:
        if proxy:
            self.bad_proxies.add(proxy)
            record_banned_proxy()
            print(f"[Proxy] Marked bad: {proxy[:40]}")

    def is_banned_response(self, status_code: int, content: str = "") -> bool:
        if status_code in BAN_STATUS_CODES:
            return True
        content_lower = content.lower()
        for keyword in BAN_KEYWORDS:
            if keyword in content_lower:
                return True
        return False

    def get_stats(self) -> dict:
        return {
            "total_proxies": len(self.proxies),
            "bad_proxies": len(self.bad_proxies),
            "available_proxies": max(0, len(self.proxies) - len(self.bad_proxies)),
            "using_proxies": self.use_proxies
        }

    def build_httpx_proxies(self, proxy: str | None) -> dict | None:
        """
        Build httpx-compatible proxy dict for httpx==0.24.1
        Returns None if no proxy (direct connection)
        """
        if not proxy:
            return None
        return {
            "http://": proxy,
            "https://": proxy,
        }

    async def scrape_free_proxies(self) -> list[str]:
        """Auto-scrape free proxies from public GitHub lists"""
        scraped = []
        sources = [
            "https://raw.githubusercontent.com/TheSpeedX/PROXY-List/master/http.txt",
            "https://raw.githubusercontent.com/clarketm/proxy-list/master/proxy-list-raw.txt",
            "https://raw.githubusercontent.com/ShiftyTR/Proxy-List/master/http.txt",
        ]
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                for source in sources:
                    try:
                        resp = await client.get(source)
                        if resp.status_code == 200:
                            lines = resp.text.strip().split('\n')
                            for line in lines[:30]:
                                line = line.strip()
                                if ':' in line and line:
                                    proxy = f"http://{line}" if not line.startswith("http") else line
                                    scraped.append(proxy)
                    except Exception:
                        continue
        except Exception as e:
            print(f"[Proxy] Scrape error: {e}")

        new_proxies = [p for p in scraped if p not in self.proxies]
        if new_proxies:
            self.proxies.extend(new_proxies)
            self.use_proxies = True
            try:
                with open("proxies.txt", "a") as f:
                    for p in new_proxies:
                        f.write(f"\n{p}")
            except Exception:
                pass
            print(f"[Proxy] Scraped {len(new_proxies)} new proxies")
        return new_proxies


# Global instance
proxy_manager = ProxyManager()
