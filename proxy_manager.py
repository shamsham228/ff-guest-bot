# proxy_manager.py
import random
import httpx
from stats_manager import record_banned_proxy

BAN_STATUS_CODES = {403, 429, 503, 407}
BAN_KEYWORDS = [
    "banned", "blocked", "rate limit",
    "too many", "captcha", "forbidden"
]


class ProxyManager:
    def __init__(self, proxy_file: str = "proxies.txt"):
        self.proxies: list[str] = []
        self.bad_proxies: set[str] = set()
        self.index: int = 0
        self.use_proxies: bool = False
        self._load(proxy_file)

    def _load(self, proxy_file: str) -> None:
        try:
            with open(proxy_file, "r") as f:
                lines = f.readlines()
            self.proxies = [
                l.strip() for l in lines
                if l.strip() and not l.strip().startswith("#")
            ]
            if self.proxies:
                self.use_proxies = True
                print(f"[Proxy] Loaded {len(self.proxies)} proxies")
            else:
                print("[Proxy] No proxies — using direct connection")
        except FileNotFoundError:
            print("[Proxy] proxies.txt not found — using direct")
            self.proxies = []

    def get(self) -> str | None:
        if not self.use_proxies or not self.proxies:
            return None
        available = [p for p in self.proxies if p not in self.bad_proxies]
        if not available:
            self.bad_proxies.clear()
            available = self.proxies
        proxy = available[self.index % len(available)]
        self.index += 1
        return proxy

    def get_random(self) -> str | None:
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

    def is_banned_response(self, status: int, body: str = "") -> bool:
        if status in BAN_STATUS_CODES:
            return True
        body_lower = body.lower()
        return any(k in body_lower for k in BAN_KEYWORDS)

    def get_stats(self) -> dict:
        return {
            "total_proxies": len(self.proxies),
            "bad_proxies": len(self.bad_proxies),
            "available_proxies": max(0, len(self.proxies) - len(self.bad_proxies)),
            "using_proxies": self.use_proxies
        }

    async def scrape_free_proxies(self) -> list[str]:
        """Auto-scrape free proxies from public GitHub lists"""
        scraped = []
        sources = [
            "https://raw.githubusercontent.com/TheSpeedX/PROXY-List/master/http.txt",
            "https://raw.githubusercontent.com/clarketm/proxy-list/master/proxy-list-raw.txt",
            "https://raw.githubusercontent.com/ShiftyTR/Proxy-List/master/http.txt",
            "https://raw.githubusercontent.com/monosans/proxy-list/main/proxies/http.txt",
        ]
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                for url in sources:
                    try:
                        r = await client.get(url)
                        if r.status_code == 200:
                            for line in r.text.strip().split('\n')[:30]:
                                line = line.strip()
                                if ':' in line and line:
                                    p = f"http://{line}" if not line.startswith("http") else line
                                    if p not in self.proxies:
                                        scraped.append(p)
                    except Exception:
                        continue
        except Exception as e:
            print(f"[Proxy] Scrape error: {e}")

        if scraped:
            self.proxies.extend(scraped)
            self.use_proxies = True
            try:
                with open("proxies.txt", "a") as f:
                    for p in scraped:
                        f.write(f"\n{p}")
            except Exception:
                pass
            print(f"[Proxy] Scraped {len(scraped)} new proxies")

        return scraped


proxy_manager = ProxyManager()
