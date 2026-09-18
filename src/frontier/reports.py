"""Escaped standalone local reports using the identical persisted result contract."""

import html
import json
from pathlib import Path


def write_report(result: dict, path: Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    summary = result["summary"]
    return_basis = (
        "Raw prices plus recorded gross cash dividends (before withholding and taxes)"
        if summary.get("return_basis") == "raw_price_plus_gross_cash_dividends"
        else "Raw prices"
    )
    if summary.get("total_return") is None:
        return_basis += "; action coverage is incomplete, so this is an exploratory NAV return"
    limitation = "".join(f"<li>{html.escape(item)}</li>" for item in summary["limitations"])
    sections = "".join(
        f"<h2>{html.escape(key.replace('_', ' ').title())}</h2>"
        f"<pre>{html.escape(json.dumps(result.get(key), indent=2))}</pre>"
        for key in (
            "summary",
            "equity_curve",
            "decisions",
            "fills",
            "positions",
            "balances",
            "dividends",
            "dividend_receivables",
            "engine_identity",
            "config",
            "dataset",
            "unfilled_intents",
            "exposure_drift",
            "evaluation_access",
        )
    )
    path.write_text(
        "<!doctype html><html lang='en'><meta charset='utf-8'>"
        "<title>Frontier research evidence</title><style>body{font:16px system-ui;"
        "max-width:1100px;margin:40px auto;background:#101923;color:#ecf2f7;padding:24px}"
        "pre{white-space:pre-wrap;background:#182635;padding:20px;overflow:auto}"
        ".notice{border:2px solid #e4ae49;padding:20px}h1{color:#7ae2bd}</style>"
        "<h1>Frontier research evidence</h1>"
        f"<p class='notice'>{html.escape(summary['evidence_label'])}</p>"
        f"<p>Return basis: {html.escape(return_basis)}.</p>"
        f"<ul>{limitation}</ul>{sections}</html>",
        encoding="utf-8",
    )
    return path
