import asyncio, pandas as pd
from datetime import datetime
from settings import settings
from datafeed.primary_ws import PrimaryWS

OUT_CSV = "assets/plots/execution_reports.csv"

async def main():
    feed = PrimaryWS(symbols=[])
    task = asyncio.create_task(feed.run())
    rows = []
    try:
        while not feed.token_value():
            await asyncio.sleep(0.05)
        print(f"[{datetime.utcnow()}] listening er for account={settings.account_for_env()}, prop={settings.proprietary_tag}")
        while True:
            er = await feed.next_exec_report()
            rows.append(dict(
                ts=er.ts.isoformat(),
                symbol=er.symbol,
                side=er.side,
                price=er.price,
                qty=er.qty,
                status=er.status,
                order_id=er.order_id,
                cl_ord_id=er.cl_ord_id,
            ))
            if len(rows) >= 20:
                df = pd.DataFrame(rows); rows.clear()
                df.to_csv(OUT_CSV, mode="a", index=False, header=not pd.io.common.file_exists(OUT_CSV))
    finally:
        if rows:
            pd.DataFrame(rows).to_csv(OUT_CSV, mode="a", index=False, header=not pd.io.common.file_exists(OUT_CSV))
        await feed.stop(); await task

if __name__ == "__main__":
    asyncio.run(main())
