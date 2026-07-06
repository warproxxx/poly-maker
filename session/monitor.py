"""One-shot health probe for the live MM session. Prints a compact status block
plus ALERT lines for anything that needs attention. Run each monitoring cycle."""
from __future__ import annotations

import asyncio
import json
import re
import subprocess
import httpx
from polymaker.config import Config
from polymaker.execution.gateway import ExecutionGateway

LOG = "session/live.log"
NEWS_Y = "54533043819946592547517511176940999955633860128497669742211153063842200957669"
NEWS_N = "87854174148074652060467921081181402357467303721471806610111179101805869578687"
FUNDER = "0xb84ca5f197A73429F608842cD75ebbC7c578e169"


def logstats(cid: str) -> dict:
    txt = open(LOG).read()
    lines = [l for l in txt.splitlines() if f"cid={cid}" in l]
    regimes = re.findall(rf"cid={cid}.*?regime=([A-Z_]+)", "\n".join(lines))
    cancels = sum(1 for l in lines if re.search(r"cancel=[1-9]", l))
    tox = [float(x) for x in re.findall(rf"cid={cid}.*?tox=([0-9.]+)", "\n".join(lines))]
    return {
        "reqs": len(lines),
        "cancels": cancels,
        "halts": sum(1 for r in regimes if r == "HALTED"),
        "last_regime": regimes[-1] if regimes else "?",
        "maxtox": max(tox) if tox else 0.0,
    }


async def main() -> None:
    alerts: list[str] = []
    engines = int(subprocess.run(["grep", "-c", "engine_started", LOG],
                                 capture_output=True, text=True).stdout.strip() or 0)
    procs = subprocess.run("pgrep -f 'polymaker run'", shell=True,
                           capture_output=True, text=True).stdout.split()
    alive = len(procs) > 0
    if not alive:
        alerts.append("BOT PROCESS DEAD")

    full = open(LOG).read()
    errors = len(re.findall(r"Traceback|quoter_error|reconcile_error|task_died|divergence", full))
    fills = len(re.findall(r"\] fill ", full))
    if errors:
        alerts.append(f"{errors} error/divergence lines in log")

    gw = ExecutionGateway(Config.load("config"))
    await gw.connect()
    naz = httpx.get("https://gamma-api.polymarket.com/markets",
                    params={"slug": "will-alexandru-nazare-be-the-next-prime-minister-of-romania"},
                    timeout=15).json()[0]
    NY, NN = json.loads(naz["clobTokenIds"])
    band = float(naz["rewardsMaxSpread"]) / 100.0

    async def mid(tok: str) -> float:
        b = httpx.get("https://clob.polymarket.com/book", params={"token_id": tok}, timeout=15).json()
        bb = max((float(x["price"]) for x in b["bids"]), default=0)
        ba = min((float(x["price"]) for x in b["asks"]), default=1)
        return (bb + ba) / 2

    naz_mid = await mid(NY)
    news_mid = await mid(NEWS_Y)
    oo = await gw.open_orders()

    def fmt(tok_yes, tok_no, m, label):
        rows = []
        n_inband = 0
        for o in oo:
            if o.token_id in (tok_yes, tok_no):
                eff = o.price if o.token_id == tok_yes else round(1 - o.price, 3)
                d = abs(eff - m)
                inb = d <= band if label == "ROM" else d <= 0.055
                n_inband += inb
                rows.append(f"{'Y' if o.token_id==tok_yes else 'N'}:{o.side.value[0]}{o.size:.0f}@{o.price}({d*100:.1f}c{'✓' if inb else '✗OUT'})")
        return rows, n_inband

    rrows, rin = fmt(NY, NN, naz_mid, "ROM")
    nrows, nin = fmt(NEWS_Y, NEWS_N, news_mid, "NEWS")

    # positions
    pos = {}
    try:
        for p in httpx.get("https://data-api.polymarket.com/positions",
                           params={"user": FUNDER}, timeout=15).json():
            if p.get("asset") in (NEWS_Y, NY, NN):
                pos[p["asset"]] = (float(p["size"]), float(p["avgPrice"]), float(p.get("curPrice", 0)))
    except Exception:
        pass
    pusd = await gw.collateral_balance()

    rs, ns = logstats("0xabc341"), logstats("0x0f49db")
    if not alive or engines != 1:
        pass
    if rs["halts"] > 0:
        alerts.append(f"ROMANIA {rs['halts']} HALTs")
    if rs["maxtox"] > 0.15 or ns["maxtox"] > 0.15:
        alerts.append(f"TOXICITY spike ROM={rs['maxtox']} NEWS={ns['maxtox']}")
    for rows, m, lbl in ((rrows, naz_mid, "ROM"), (nrows, news_mid, "NEWS")):
        if any("OUT" in r for r in rows):
            alerts.append(f"{lbl} order OUT OF BAND")
    if NY in pos or NN in pos:
        alerts.append(f"ROMANIA FILLED: {[(k[:6], round(v[0])) for k,v in pos.items() if k in (NY,NN)]}")

    ny = pos.get(NEWS_Y, (668, 0.1917, news_mid))
    news_unreal = ny[0] * (ny[2] - ny[1]) if ny[2] else 0.0

    print(f"engines={engines} alive={alive} fills={fills} errors={errors} pUSD={pusd:.0f}")
    print(f"NEWSOM  mid={news_mid:.3f} pos={ny[0]:.0f}Y@{ny[1]:.4f} unreal=${news_unreal:+.2f} "
          f"| {' '.join(nrows)} inband={nin} | reg={ns['last_regime']} reqs={ns['reqs']} cxl={ns['cancels']} halt={ns['halts']} tox={ns['maxtox']}")
    print(f"ROMANIA mid={naz_mid:.3f} pos={'FILLED' if (NY in pos or NN in pos) else 'flat'} "
          f"| {' '.join(rrows)} inband={rin} | reg={rs['last_regime']} reqs={rs['reqs']} cxl={rs['cancels']} halt={rs['halts']} tox={rs['maxtox']}")
    print("ALERTS: " + ("  ||  ".join(alerts) if alerts else "none — all nominal"))


asyncio.run(main())
