"""Independent saved-response verification; no transport, credentials or probe imports."""
from datetime import datetime
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import re
from urllib.parse import parse_qs, urlsplit

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parents[1]


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    definition, review, summary = (read(ROOT / name) for name in
        ["request-definition.json", "execution-review.json", "summary.json"])
    for name, digest in review["verified_sha256"].items():
        assert sha(ROOT / name) == digest, name
    for name, digest in definition["existing_input_sha256"].items():
        assert sha(REPO / name) == digest, name
    assert read(ROOT / "attempt.json") == summary
    assert summary["status"] == "complete" and summary["network_requests"] == 3
    assert summary["historical_quote_requests"] == 0
    assert len(summary["requests"]) == len(definition["metadata_probe"]["requests"]) == 3
    expected = set(definition["scope"]["symbols"])
    records, raw_ids, starts = [], {}, []
    saved = {c["symbol"]: c for c in summary["contracts"]}
    for request, response in zip(definition["metadata_probe"]["requests"], summary["requests"], strict=True):
        assert request["id"] == response["id"]
        url = urlsplit(response["url"])
        assert url.scheme == "https" and url.netloc == "paper-api.alpaca.markets" and url.path == "/v2/options/contracts"
        assert parse_qs(url.query) == {k: [str(v)] for k, v in request["params"].items()}
        assert response["http_status"] == 200 and response["status"] == "captured" and not response["truncated"]
        raw = ROOT / response["raw"]
        assert sha(raw) == response["sha256"] and raw.stat().st_size == response["bytes"] <= 1048576
        raw_ids[response["raw"]] = response["sha256"]
        body = read(raw)
        assert not body.get("next_page_token") and not body.get("page_token")
        rows = body["option_contracts"]
        assert len(rows) == 2 and {r["symbol"] for r in rows} == set(request["expected_symbols"])
        start, end = map(datetime.fromisoformat, [response["started_at"], response["received_at"]])
        assert 0 <= (end-start).total_seconds() <= 60
        starts.append(start)
        for row in rows:
            symbol = row["symbol"]
            match = re.fullmatch(r"SPY(\d{6})([CP])(\d{8})", symbol)
            assert match and match[1] == "240315" and symbol in expected
            assert row["type"] == {"C": "call", "P": "put"}[match[2]]
            assert Decimal(row["strike_price"]) == Decimal(match[3])/1000
            assert row["expiration_date"] == "2024-03-15" and row["root_symbol"] == row["underlying_symbol"] == "SPY"
            assert row["status"] == "inactive" and row["tradable"] is False and row["style"] == "american"
            assert Decimal(row["size"]) == 100
            assert len(row["deliverables"]) == 1
            deliverable = row["deliverables"][0]
            assert deliverable["type"] == "equity" and deliverable["symbol"] == "SPY"
            assert deliverable["asset_id"] == row["underlying_asset_id"]
            assert Decimal(deliverable["amount"]) == Decimal(deliverable["allocation_percentage"]) == 100
            assert row == saved[symbol]["terms"] and saved[symbol]["status"] == "matched"
            records.append({"symbol": symbol, "source_sha256": response["sha256"], "id": row["id"],
                "size": row["size"], "multiplier": row.get("multiplier"), "deliverables": row["deliverables"],
                "open_interest_date": row.get("open_interest_date"), "close_price_date": row.get("close_price_date"),
                "identity_qualified": True, "pricing_multiplier_semantics_qualified": False,
                "historical_term_vintage_qualified": False})
    assert {r["symbol"] for r in records} == expected and len(records) == len({r["id"] for r in records}) == 6
    spacing = [(b-a).total_seconds() for a,b in zip(starts,starts[1:])]
    assert min(spacing) >= 3
    report = {"status": "raw_identity_checks_passed_with_semantic_gaps", "http_requests": 3,
        "historical_quote_requests": 0, "raw_bytes": sum(r["bytes"] for r in summary["requests"]),
        "raw_sha256": raw_ids, "request_start_spacing_seconds": spacing,
        "source_review_precedes_first_request": datetime.fromisoformat(review["reviewed_at"]) < starts[0],
        "contracts": records, "missing_or_ambiguous_contracts": [],
        "summary_sha256": sha(ROOT / "summary.json"), "checker_sha256": sha(Path(__file__)),
        "limitations": [
            "All six provider records literally report multiplier=0 although size=100 and the deliverable is 100 SPY shares. This verifies source fields, not pricing multiplier semantics; no replacement or cash conversion is authorized.",
            "All six deliverables report T+1 at retrospective retrieval; this does not establish settlement rules or terms known in February/March 2024.",
            "Open-interest and close-price dates are March 15, 2024, later than the February fixture; these are not historical features for that fixture.",
            "No historical OPRA quotes, historical as-of chain membership, complete contract-action history, fills, exercise cashflows or performance are qualified."],
        "new_network_requests_by_checker": 0}
    assert report["source_review_precedes_first_request"]
    with (ROOT / "independent-verification.json").open("x", encoding="utf-8") as stream:
        json.dump(report, stream, indent=2, allow_nan=False)
        stream.write("\n")
    print(json.dumps({k: report[k] for k in ["status", "http_requests", "historical_quote_requests", "raw_bytes", "missing_or_ambiguous_contracts"]}))


if __name__ == "__main__":
    main()
