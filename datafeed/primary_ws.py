import asyncio, json
import pandas as pd
import requests
import websockets
from typing import Dict, List, Optional
from .base import Quote2, DataFeedWS
from settings import settings

AUTH_HDR = "X-Auth-Token"

class PrimaryWS(DataFeedWS):
    def __init__(self, symbols: List[str]):
        rest, ws = settings.urls()
        self.base_rest = rest.rstrip("/")
        self.ws_url = ws
        self.user, self.pwd = settings.auth_creds()
        self.timeout = settings.primary_timeout_s
        self.symbols = symbols
        self.token: Optional[str] = None
        self.ws = None
        self._cache: Dict[str, Quote2] = {}
        self._lock = asyncio.Lock()
        self._stop = False

    def subscribed_symbols(self) -> List[str]:
        return list(self.symbols)

    def snapshot(self) -> Dict[str, Quote2]:
        return dict(self._cache)

    def login(self) -> str:
        r = requests.post(
            f"{self.base_rest}/auth/getToken",
            headers={"X-Username": self.user, "X-Password": self.pwd},
            timeout=self.timeout,
        )
        r.raise_for_status()
        tok = r.headers.get(AUTH_HDR)
        if not tok:
            raise RuntimeError("no token en headers")
        self.token = tok
        return tok

    async def _connect(self):
        if not self.token:
            self.login()
        q = f"{self.ws_url}?{AUTH_HDR}={self.token}"
        self.ws = await websockets.connect(q, ping_interval=15, ping_timeout=10)
        sub = {"type": "smd", "level": 1, "symbols": self.symbols, "entries": ["BI", "OF"]}
        await self.ws.send(json.dumps(sub))

    async def _consume(self):
        async for msg in self.ws:
            try:
                j = json.loads(msg)
            except Exception:
                continue
            if j.get("type") != "md":
                continue
            sym = j.get("symbol")
            e = j.get("entries", {})
            bi = (e.get("BI") or [{}])[0]
            of = (e.get("OF") or [{}])[0]
            q = Quote2(
                ts=pd.Timestamp.utcnow(),
                bid=float(bi.get("price", 0) or 0),
                ask=float(of.get("price", 0) or 0),
                bid_qty=float(bi.get("size", 0) or 0),
                ask_qty=float(of.get("size", 0) or 0),
            )
            async with self._lock:
                self._cache[sym] = q

    async def run(self):
        backoff = 1.0
        while not self._stop:
            try:
                await self._connect()
                backoff = 1.0
                await self._consume()
            except websockets.ConnectionClosed:
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 30.0)
                try: self.login()
                except Exception: pass
            except Exception:
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 30.0)

    async def stop(self):
        self._stop = True
        try:
            if self.ws:
                await self.ws.close()
        except Exception:
            pass
