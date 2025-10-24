from dataclasses import dataclass
from typing import Dict, List, Optional
from pandas import Timestamp

@dataclass
class Quote2:
    ts: Timestamp
    bid: float
    ask: float
    bid_qty: float
    ask_qty: float

class DataFeedWS:
    async def run(self): ...
    def snapshot(self) -> Dict[str, Quote2]: ...
    def subscribed_symbols(self) -> List[str]: ...

@dataclass
class ExecReport:
    ts: Timestamp
    symbol: str
    side: str
    price: float
    qty: float
    status: str
    order_id: Optional[str] = None
    cl_ord_id: Optional[str] = None
