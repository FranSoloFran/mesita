import asyncio, pandas as pd
from settings import settings
from discover.instruments import build_pairs
from datafeed.primary_ws import PrimaryWS
from sim.mep_ref import MEPRef

def implied_a2u(qa, qu): return (qa.ask/qu.bid) if (qa and qu and qa.ask>0 and qu.bid>0) else None
def implied_u2a(qa, qu): return (qa.bid/qu.ask) if (qa and qu and qa.bid>0 and qu.ask>0) else None

async def main():
    pairs = build_pairs()
    ref_pair = next((p for p in pairs if p[0].upper()=="AL30" and p[1].upper()=="AL30D"), pairs[0])
    symbols = sorted({s for a,b in pairs for s in (a,b)})
    feed = PrimaryWS(symbols)
    ref = MEPRef(120)
    task = asyncio.create_task(feed.run())
    try:
        while True:
            snap = feed.snapshot()
            if ref_pair[0] in snap and ref_pair[1] in snap:
                qa_ref, qu_ref = snap[ref_pair[0]], snap[ref_pair[1]]
                ref.update(qa_ref.ask, qu_ref.bid, qa_ref.bid, qu_ref.ask)
                a2u_ref, u2a_ref = ref.mep_ref_ars_to_usd, ref.mep_ref_usd_to_ars
                rows = []
                for ars_sym, usd_sym in pairs:
                    qa, qu = snap.get(ars_sym), snap.get(usd_sym)
                    rows.append(dict(
                        pair=f"{ars_sym}:{usd_sym}",
                        bid_ars=getattr(qa,"bid",None),
                        ask_ars=getattr(qa,"ask",None),
                        bid_usd=getattr(qu,"bid",None),
                        ask_usd=getattr(qu,"ask",None),
                        implied_a2u=implied_a2u(qa, qu),
                        implied_u2a=implied_u2a(qa, qu),
                    ))
                print(pd.DataFrame(rows).to_string(index=False))
                if a2u_ref and u2a_ref:
                    print(f"mep_ref a2u={a2u_ref:.2f} u2a={u2a_ref:.2f}")
                else:
                    print("mep_ref warming up…")
            await asyncio.sleep(settings.poll_s)
    finally:
        await feed.stop(); await task

if __name__ == "__main__":
    asyncio.run(main())
