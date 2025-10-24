import asyncio, json
import pandas as pd
import requests, websockets
from typing import Dict, List, Optional
from .base import Quote2, DataFeedWS, ExecReport
from settings import settings
from util.trace import Trace

AUTH_HDR = "X-Auth-Token"

class PrimaryWS(DataFeedWS):
    def __init__(self, symbols: List[str]):
        rest, ws = settings.urls()
        self.base_rest = rest.rstrip("/")
        self.ws_url = ws
        self.user, self.pwd = settings.auth_creds()
        self.timeout = settings.primary_timeout_s
        self.symbols = sorted(set(symbols))
        self.token: Optional[str] = None
        self.ws = None
        self._cache: Dict[str, Quote2] = {}
        self._lock = asyncio.Lock()
        self._stop = False
        self._er_queue: asyncio.Queue[ExecReport] = asyncio.Queue()
        self._account = settings.account_for_env()
        self._prop = settings.proprietary_tag
        self._trace = Trace(settings.trace_path, settings.trace_rotate_mb) if settings.trace_enabled else None

    def subscribed_symbols(self) -> List[str]: return list(self.symbols)
    def snapshot(self) -> Dict[str, Quote2]: return dict(self._cache)
    def token_value(self) -> str: return self.token

    def login(self) -> str:
        r = requests.post(
            f"{self.base_rest}/auth/getToken",
            headers={"X-Username": self.user, "X-Password": self.pwd},
            timeout=self.timeout,
        ); r.raise_for_status()
        tok = r.headers.get(AUTH_HDR)
        if not tok: raise RuntimeError("no token")
        self.token = tok
        if self._trace: self._trace.log("auth.token", ok=True, env=settings.env)
        return tok

    async def _connect(self):
        if not self.token: self.login()
        q = f"{self.ws_url}?{AUTH_HDR}={self.token}"
        if self._trace: self._trace.log("ws.connect.start", url=self.ws_url)
        self.ws = await websockets.connect(q, ping_interval=15, ping_timeout=10)
        if self._trace: self._trace.log("ws.connect.ok", subscribed=len(self.symbols))
        if self.symbols:
            await self._send({"type":"smd","level":1,"symbols":self.symbols,"entries":["BI","OF"]})
        await self._send({"type":"spr","accounts":[self._account],"all":True})

    async def _send(self, obj: dict):
        if self._trace and settings.trace_raw:
            try: self._trace.log("ws.send", payload=obj)
            except Exception: pass
        await self.ws.send(json.dumps(obj))

    async def update_symbols(self, new_symbols: List[str]):
        self.symbols = sorted(set(new_symbols))
        gone = [k for k in list(self._cache.keys()) if k not in self.symbols]
        for k in gone: self._cache.pop(k, None)
        if self.ws:
            await self._send({"type":"smd","level":1,"symbols":self.symbols,"entries":["BI","OF"]})
        if self._trace: self._trace.log("md.resub", symbols=len(self.symbols))

    async def send_limit(self, symbol: str, side: str, qty: int, price: float, tif: str="DAY", iceberg: bool=False, display_qty: int|None=None) -> str:
        payload = {
            "type":"no",
            "product":{"marketId":"ROFX","symbol":symbol},
            "price":price,
            "quantity":qty,
            "side":side,
            "account":self._account,
            "timeInForce":tif,
            "iceberg":bool(iceberg),
            "proprietary":self._prop
        }
        if iceberg and display_qty:
            payload["displayQuantity"] = display_qty
        await self._send(payload)
        if self._trace:
            self._trace.log("order.send", kind="limit", symbol=symbol, side=side, qty=qty, price=price, tif=tif)
        return "SENT"

    async def send_market(self, symbol: str, side: str, qty: int, tif: str="IOC"):
        payload = {
            "type":"no",
            "product":{"marketId":"ROFX","symbol":symbol},
            "quantity":qty,
            "side":side,
            "account":self._account,
            "ordType":"MARKET",
            "timeInForce":tif,
            "proprietary":self._prop
        }
        await self._send(payload)
        if self._trace:
            self._trace.log("order.send", kind="market", symbol=symbol, side=side, qty=qty, tif=tif)
        return "SENT"

    async def _consume(self):
        async for raw in self.ws:
            try:
                j = json.loads(raw)
            except Exception:
                continue
            t = j.get("type")
            if t == "md":
                sym = j.get("symbol")
                e = j.get("entries", {})
                bi = (e.get("BI") or [{}])[0]
                of = (e.get("OF") or [{}])[0]
                q = Quote2(
                    ts=pd.Timestamp.utcnow(),
                    bid=float(bi.get("price",0) or 0),
                    ask=float(of.get("price",0) or 0),
                    bid_qty=float(bi.get("size",0) or 0),
                    ask_qty=float(of.get("size",0) or 0),
                )
                async with self._lock:
                    self._cache[sym]=q
                if self._trace and settings.trace_raw:
                    self._trace.log("md", symbol=sym, bid=q.bid, ask=q.ask, bid_qty=q.bid_qty, ask_qty=q.ask_qty)
            elif t == "er":
                er = ExecReport(
                    ts=pd.Timestamp.utcnow(),
                    symbol=j.get("product",{}).get("symbol",""),
                    side=j.get("side",""),
                    price=float(j.get("lastPx", j.get("price",0)) or 0),
                    qty=float(j.get("lastQty", j.get("quantity",0)) or 0),
                    status=j.get("status",""),
                    order_id=str(j.get("orderId","") or ""),
                    cl_ord_id=str(j.get("clOrdId","") or ""),
                )
                await self._er_queue.put(er)
                if self._trace:
                    self._trace.log("er", symbol=er.symbol, side=er.side, price=er.price, qty=er.qty, status=er.status, order_id=er.order_id)
            else:
                pass

    async def run(self):
        backoff = 1.0
        while not self._stop:
            try:
                await self._connect()
                backoff = 1.0
                await self._consume()
            except websockets.ConnectionClosed:
                await asyncio.sleep(backoff); backoff=min(backoff*2,30.0)
                try: self.login()
                except Exception: pass
            except Exception:
                await asyncio.sleep(backoff); backoff=min(backoff*2,30.0)

    async def stop(self):
        self._stop = True
        try:
            if self.ws: await self.ws.close()
        except Exception: pass

    async def next_exec_report(self) -> ExecReport:
        return await self._er_queue.get()
