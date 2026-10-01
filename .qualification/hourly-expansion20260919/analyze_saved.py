"""Offline source validation; performs no network or account access."""
import hashlib
import json
from pathlib import Path

import exchange_calendars as xcals
import numpy as np
import pandas as pd

root = Path(__file__).resolve().parent
result = {"capture_integrity": [], "hourly": {}, "minute": {}}
for path in sorted(root.glob("*.capture.json")):
    meta = json.loads(path.read_text())
    raw = (root / meta["raw_file"]).read_bytes()
    assert hashlib.sha256(raw).hexdigest() == meta["sha256"]
    body = json.loads(raw)
    assert not body.get("next_page_token"), "Source response is not complete"
    result["capture_integrity"].append({"name": meta["name"], "sha256": meta["sha256"], "bytes": len(raw)})
    for symbol, values in (body.get("bars") or {}).items():
        frame = pd.DataFrame(values)
        frame["t"] = pd.to_datetime(frame["t"], utc=True)
        assert not frame.t.duplicated().any()
        assert frame.t.is_monotonic_increasing
        assert np.isfinite(frame[["o", "h", "l", "c", "v"]]).all().all()
        assert (frame[["o", "h", "l", "c"]] > 0).all().all()
        assert (frame.v >= 0).all()
        assert (frame.h >= frame[["o", "c", "l"]].max(axis=1)).all()
        assert (frame.l <= frame[["o", "c", "h"]].min(axis=1)).all()
        if meta["params"]["timeframe"] == "1Hour":
            calendar = xcals.get_calendar("XNYS", start="2016-01-01", end="2016-01-15")
            categories = {"fully_regular_session": 0, "crosses_regular_open": 0, "outside_regular_session": 0}
            for timestamp in frame.t:
                session = str(timestamp.tz_convert("America/New_York").date())
                if not calendar.is_session(session):
                    categories["outside_regular_session"] += 1
                    continue
                opening, closing = calendar.session_open(session), calendar.session_close(session)
                end = timestamp + pd.Timedelta(hours=1)
                if opening <= timestamp and end <= closing:
                    categories["fully_regular_session"] += 1
                elif timestamp < opening < end:
                    categories["crosses_regular_open"] += 1
                else:
                    categories["outside_regular_session"] += 1
            result["hourly"][symbol] = {"rows": len(frame), "timestamp_minute_values": sorted(frame.t.dt.minute.unique().tolist()), **categories}
        else:
            calendar = xcals.get_calendar("XNYS", start="2024-11-25", end="2024-12-02")
            opening = calendar.session_open("2024-11-29")
            closing = calendar.session_close("2024-11-29")
            expected = pd.date_range(opening, closing, freq="min", inclusive="left")
            assert frame.t.tolist() == expected.tolist()
            rows = []
            for start in pd.date_range(opening, closing, freq="h", inclusive="left"):
                end = min(start + pd.Timedelta(hours=1), closing)
                minute = frame[(frame.t >= start) & (frame.t < end)]
                rows.append({"symbol": symbol, "start": start.isoformat(), "end": end.isoformat(), "duration_minutes": int((end-start).total_seconds()/60), "source_minutes": len(minute), "open": float(minute.o.iloc[0]), "high": float(minute.h.max()), "low": float(minute.l.min()), "close": float(minute.c.iloc[-1]), "volume": float(minute.v.sum()), "trade_count": int(minute.n.sum()), "vwap": float((minute.v * minute.vw).sum()/minute.v.sum())})
            assert [row["source_minutes"] for row in rows] == [60,60,60,30]
            assert sum(row["volume"] for row in rows) == frame.v.sum()
            result["minute"][symbol] = {"rows": len(frame), "missing_regular_minutes": 0, "session_open_utc": opening.isoformat(), "session_close_utc": closing.isoformat(), "session_aligned_hours": rows, "volume_reconciles": True}
result["notes"] = ["Raw feed captures are current retrieved vintages, not historical availability snapshots.", "Provider hourly timestamps denote clock-hour starts; opening-crossing bars cannot be cropped into session-aligned OHLC.", "Minute aggregation is an offline derived source fixture, not an imported trading dataset or strategy test."]
(root/'offline-analysis.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
print(json.dumps({"hashes_verified": len(result['capture_integrity']), "hourly":result['hourly'], "minute":{symbol:{key:value for key,value in row.items() if key!='session_aligned_hours'} for symbol,row in result['minute'].items()}}, indent=2))
