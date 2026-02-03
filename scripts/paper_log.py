import argparse
import csv
import json
import os
import time
import urllib.request
from datetime import datetime, time as dt_time, timezone
from zoneinfo import ZoneInfo


RTH_START = dt_time(9, 30)
RTH_END = dt_time(16, 0)
EASTERN = ZoneInfo("America/New_York")


def fetch_score(base_url: str, ticker: str) -> dict:
    url = f"{base_url}/score?ticker={ticker}"
    with urllib.request.urlopen(url, timeout=10) as resp:
        return json.loads(resp.read().decode())


def range_pair(levels: dict, key: str):
    val = levels.get(key)
    if isinstance(val, list) and len(val) == 2:
        return val[0], val[1]
    return None, None


def session_tag(ts_iso: str | None) -> str | None:
    if not ts_iso:
        return None
    try:
        dt = datetime.fromisoformat(ts_iso)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)

    dt_et = dt.astimezone(EASTERN)
    if dt_et.weekday() >= 5:
        return "EXT"

    t = dt_et.time()
    return "RTH" if RTH_START <= t < RTH_END else "EXT"


def thin_gate_status(audit: list[str] | None) -> str | None:
    for entry in audit or []:
        if entry.startswith("thin_volume_gate:"):
            if "fail" in entry:
                return "fail"
            if "pass" in entry:
                return "pass"
            if "skipped" in entry:
                return "skipped"
    return None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--ticker", required=True, help="Ticker, e.g., SPY.US")
    parser.add_argument("--minutes", type=int, default=10, help="Total minutes to log")
    parser.add_argument("--interval", type=int, default=60, help="Seconds between samples")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000", help="API base URL")
    args = parser.parse_args()

    os.makedirs("data", exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    out_path = f"data/score_log_{args.ticker.replace('.', '_')}_{ts}.csv"

    fields = [
        "ts_utc",
        "ticker",
        "signal",
        "state",
        "confidence",
        "suggested_size",
        "last_price",
        "last_price_ts",
        "last_price_source",
        "session",
        "relvol_5m",
        "relvol_15m",
        "thin_volume_gate",
        "entry_low",
        "entry_high",
        "stop",
        "tp1",
        "tp2",
        "support_low",
        "support_high",
        "res1_low",
        "res1_high",
        "res2_low",
        "res2_high",
        "missing_timeframes",
    ]

    total = max(1, int((args.minutes * 60) / args.interval))

    with open(out_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()

        for _ in range(total):
            data = fetch_score(args.base_url, args.ticker)
            levels = data.get("levels", {})
            indicators = data.get("indicators", {})
            relvol = indicators.get("relvol", {})

            relvol_5m_val = (relvol.get("5m") or {}).get("relvol20")
            relvol_15m_val = (relvol.get("15m") or {}).get("relvol20")

            entry_low, entry_high = range_pair(levels, "entry_range")
            support_low, support_high = range_pair(levels, "support_range")
            res1_low, res1_high = range_pair(levels, "resistance_1")
            res2_low, res2_high = range_pair(levels, "resistance_2")

            targets = levels.get("targets") or []
            tp1 = targets[0] if len(targets) > 0 else None
            tp2 = targets[1] if len(targets) > 1 else None

            row = {
                "ts_utc": datetime.now(timezone.utc).isoformat(),
                "ticker": data.get("ticker"),
                "signal": data.get("signal"),
                "state": data.get("state"),
                "confidence": data.get("confidence"),
                "suggested_size": data.get("suggested_size"),
                "last_price": data.get("last_price"),
                "last_price_ts": data.get("last_price_ts"),
                "last_price_source": data.get("last_price_source"),
                "session": session_tag(data.get("last_price_ts")),
                "relvol_5m": relvol_5m_val,
                "relvol_15m": relvol_15m_val,
                "thin_volume_gate": thin_gate_status(data.get("audit")),
                "entry_low": entry_low,
                "entry_high": entry_high,
                "stop": levels.get("stop"),
                "tp1": tp1,
                "tp2": tp2,
                "support_low": support_low,
                "support_high": support_high,
                "res1_low": res1_low,
                "res1_high": res1_high,
                "res2_low": res2_low,
                "res2_high": res2_high,
                "missing_timeframes": ",".join(data.get("missing_timeframes", [])),
            }

            writer.writerow(row)
            f.flush()
            time.sleep(args.interval)

    print(f"wrote {out_path}")


if __name__ == "__main__":
    main()
