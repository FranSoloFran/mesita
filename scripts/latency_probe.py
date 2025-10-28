import asyncio, time
from settings import settings
from datafeed.primary_ws import PrimaryWS

"""
cómo usar:
  ENV=paper (o live) en .env
  python scripts/latency_probe.py AL30 BUY 1 0.01
    => símbolo, side, qty, price
tips:
  - poné un precio "imposible" + IOC para que no ejecute y vuelva er rápido.
  - corre varias veces y promediá.
"""

import sys

async def main():
    if len(sys.argv) < 5:
        print("usage: python scripts/latency_probe.py <SYMBOL> <BUY|SELL> <QTY> <PRICE>")
        return
    symbol = sys.argv[1]
    side = sys.argv[2].upper()
    qty = int(sys.argv[3])
    price = float(sys.argv[4])

    feed = PrimaryWS(symbols=[symbol])
    task = asyncio.create_task(feed.run())

    while not feed.token_value():
        await asyncio.sleep(0.05)

    clid = await feed.send_limit(symbol=symbol, side=side, qty=qty, price=price, tif="IOC")
    t0 = time.time()
    print(f"sent clOrdId={clid} @ {t0:.6f}")

    while True:
        er = await feed.next_exec_report()
        if er.cl_ord_id == clid:
            dt = (time.time() - t0) * 1000.0
            print(f"er for {clid}: status={er.status} rtt_ms={dt:.1f}")
            break

    await feed.stop(); await task

if __name__ == "__main__":
    asyncio.run(main())
