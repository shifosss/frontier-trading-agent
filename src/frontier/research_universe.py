"""Dated research membership from public exchange directories, never the paper universe.

These are current listings, not a survivorship-free historical security master.
TMX issuer roots are resolved against its current security directory when available.
All symbols still require a price-provider identity and currency check. Only predeclared
project ETFs are eligible because the directories lack reliable leverage classifications.
"""

import csv
import hashlib
import io
import json
import re
import xml.etree.ElementTree as ET
import zipfile
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from string import ascii_uppercase

import httpx

NASDAQ_URL = "https://www.nasdaqtrader.com/dynamic/SymDir/nasdaqlisted.txt"
OTHER_URL = "https://www.nasdaqtrader.com/dynamic/SymDir/otherlisted.txt"
TMX_URL = "https://www.tsx.com/en/resource/571"
CSE_URL = "https://thecse.com/api/webapi/listed-companies/"
CBOE_CA_URL = "https://www-api.cboe.com/ca/equities/listing-directory-data/"
TMX_DIRECTORY_URL = "https://www.tsx.com/json/company-directory/search/{exchange}/{letter}"
SOURCES = {
    "nasdaq": NASDAQ_URL,
    "other_us": OTHER_URL,
    "tsx": TMX_URL,
    "cse": CSE_URL,
    "cboe_ca": CBOE_CA_URL,
}
CANADIAN_SOURCES = {"tsx", "tsxv", "cse", "cboe_ca"}
EXCHANGES = {
    "A": "NYSE American",
    "N": "NYSE",
    "P": "NYSE Arca",
    "Z": "Cboe BZX",
    "V": "IEX",
    "L": "LTSE",
    "F": "Texas Stock Exchange",
    "T": "Nasdaq Texas",
}
XML_NS = {"s": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
LIMITATIONS = [
    "Membership was discovered at capture time; it is not historical index membership.",
    "Backtests on this universe have survivorship and current-membership selection bias.",
    "Directory inclusion does not establish liquidity, broker availability or an investment edge.",
    "Canadian coverage includes TSX, TSXV, CSE and Cboe Canada; NEX is not complete.",
    "TMX monthly publication may lag new listings and delistings; preserve its stated vintage.",
    "TMX share classes use the official directory; unmatched monthly roots remain candidates.",
    "Canadian USD-quoted listings are excluded until mixed-calendar USD books are supported.",
    "US coverage includes ordinary/common shares and equity ADRs, excluding OTC listings.",
    "Current status flags are retained; they cannot establish historical trading eligibility.",
    "ETF eligibility is limited to the existing reviewed project list; leverage is not inferred.",
    "No issuer-level deduplication across US and Canadian interlistings is claimed.",
]


def _digest(content):
    return hashlib.sha256(content).hexdigest()


def _write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, allow_nan=False), encoding="utf-8")


def parse_nasdaq_directory(content, source_id):
    """Read official flags and names; do not infer security type from ticker length."""
    text = content.decode("utf-8-sig") if isinstance(content, bytes) else content
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    footer = [line.split("|", 1)[0] for line in lines if line.startswith("File Creation Time:")]
    if len(footer) != 1:
        raise ValueError("Nasdaq directory must contain one file creation timestamp")
    rows = list(
        csv.DictReader([x for x in lines if not x.startswith("File Creation Time:")], delimiter="|")
    )
    symbol_key = "Symbol" if source_id == "nasdaq" else "ACT Symbol"
    required = {symbol_key, "Security Name", "ETF", "Test Issue"}
    if not rows or not required.issubset(rows[0]):
        raise ValueError("Nasdaq directory schema differs from the documented fields")
    records = []
    for row in rows:
        source_symbol = row[symbol_key].strip()
        records.append(
            {
                "source_id": source_id,
                "source_symbol": source_symbol,
                "symbol": source_symbol.replace(".", "-"),
                "name": row["Security Name"].strip(),
                "currency": "USD",
                "calendar": "XNYS",
                "exchange": "Nasdaq" if source_id == "nasdaq" else EXCHANGES.get(row["Exchange"]),
                "is_test": row["Test Issue"] != "N",
                "is_etf": row["ETF"] == "Y",
                "financial_status": row.get("Financial Status"),
                "next_shares": row.get("NextShares") == "Y",
                "symbol_identity": "exchange_security_symbol",
            }
        )
    return records, footer[0].removeprefix("File Creation Time:").strip()


def _xlsx_rows(content):
    """Read the published workbook's values with stdlib; no Excel runtime required."""
    with zipfile.ZipFile(io.BytesIO(content)) as book:
        strings = [
            "".join(t.itertext())
            for t in ET.fromstring(book.read("xl/sharedStrings.xml")).findall("s:si", XML_NS)
        ]
        relationships = ET.fromstring(book.read("xl/_rels/workbook.xml.rels"))
        targets = {item.attrib["Id"]: item.attrib["Target"] for item in relationships}
        sheets = ET.fromstring(book.read("xl/workbook.xml")).findall("s:sheets/s:sheet", XML_NS)
        for sheet in sheets:
            rel = sheet.attrib[
                "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"
            ]
            target = targets[rel].lstrip("/")
            path = target if target.startswith("xl/") else "xl/" + target
            rows = []
            for row in ET.fromstring(book.read(path)).findall("s:sheetData/s:row", XML_NS):
                values = {}
                for cell in row.findall("s:c", XML_NS):
                    value = cell.find("s:v", XML_NS)
                    text = "" if value is None else value.text or ""
                    if cell.attrib.get("t") == "s":
                        text = strings[int(text)]
                    elif cell.attrib.get("t") == "inlineStr":
                        text = "".join(cell.find("s:is", XML_NS).itertext())
                    values[re.sub(r"[0-9]+", "", cell.attrib["r"])] = text
                rows.append(values)
            yield sheet.attrib["name"], rows


def parse_tmx_workbook(content):
    """Preserve TMX issuer-root identity, source month and published liquidity metadata."""
    records = []
    vintages = []
    for sheet, rows in _xlsx_rows(content):
        if not sheet.startswith(("TSX Issuers ", "TSXV Issuers ")):
            continue
        exchange = sheet.split(" Issuers ", 1)[0]
        vintages.append(sheet.split(" Issuers ", 1)[1])
        headers = None
        for row in rows:
            normalized = {col: " ".join(value.split()) for col, value in row.items()}
            if "Root Ticker" in normalized.values() and "Exchange" in normalized.values():
                headers = normalized
                continue
            if headers is None:
                continue
            item = {headers[col]: value for col, value in row.items() if col in headers}
            root = item.get("Root Ticker", "").strip()
            if item.get("Exchange") != exchange or not root:
                continue

            def number(prefix):
                value = next((value for key, value in item.items() if key.startswith(prefix)), "")
                return float(value) if value else None

            records.append(
                {
                    "source_id": exchange.lower(),
                    "source_symbol": root,
                    "symbol": root.replace(".", "-") + (".TO" if exchange == "TSX" else ".V"),
                    "name": item["Name"].strip(),
                    "currency": "CAD",
                    "calendar": "XTSE",
                    "exchange": exchange,
                    "sector": item.get("Sector", ""),
                    "listing_type": item.get("Listing Type", ""),
                    "product_type": item.get("SP_Type", ""),
                    "is_etf": item.get("SP_Type") == "Exchange Traded Funds",
                    "is_test": False,
                    "symbol_identity": "issuer_root_requires_provider_verification",
                    "source_vintage": vintages[-1],
                    "market_cap_cad": number("Market Cap (C$)"),
                    "ytd_value_cad": number("Value (C$) YTD"),
                    "listing_date": item.get("Listing Date"),
                    "interlisted": [
                        item[key]
                        for key in ("Interlisted I", "Interlisted II", "Interlisted")
                        if item.get(key)
                    ],
                }
            )
    if not records:
        raise ValueError("TMX workbook has no issuer records with the expected headers")
    return records, ", ".join(dict.fromkeys(vintages))


def parse_cse_directory(content):
    rows = json.loads(content)
    required = {"symbol", "security_name", "security_type", "currency", "status", "listing_market"}
    if not isinstance(rows, list) or not rows or any(not required <= row.keys() for row in rows):
        raise ValueError("CSE directory schema differs from the public listing feed")
    records = []
    for row in rows:
        symbol = row["symbol"]
        records.append(
            {
                "source_id": "cse",
                "source_symbol": symbol,
                "symbol": symbol.replace(".", "-") + ".CN",
                "name": row["security_name"],
                "currency": row["currency"],
                "calendar": "XTSE",
                "exchange": row["listing_market"],
                "sector": row.get("sector", ""),
                "listing_date": row.get("listing_date"),
                "listing_status": row["status"],
                "directory_security_type": row["security_type"],
                "is_etf": row["security_type"] == "ETF",
                "is_test": False,
                "symbol_identity": "exchange_security_symbol",
            }
        )
    return records, "current directory; no publication timestamp supplied"


def parse_cboe_canada_directory(content):
    rows = json.loads(content).get("data")
    required = {"symbol", "name", "currency", "security", "security_sub_type"}
    if not isinstance(rows, list) or not rows or any(not required <= row.keys() for row in rows):
        raise ValueError("Cboe Canada directory schema differs from the public listing feed")
    return [
        {
            "source_id": "cboe_ca",
            "source_symbol": row["symbol"],
            "symbol": row["symbol"].replace(".", "-") + ".NE",
            "name": row["name"],
            "currency": row["currency"],
            "calendar": "XTSE",
            "exchange": "Cboe Canada",
            "directory_security_type": row["security"],
            "directory_security_subtype": row["security_sub_type"],
            "is_etf": row["security"] == "etf",
            "is_test": False,
            "symbol_identity": "exchange_security_symbol",
        }
        for row in rows
    ], "current directory; no publication timestamp supplied"


def parse_tmx_directory(content):
    document = json.loads(content)
    rows = document.get("results")
    if (
        not isinstance(rows, list)
        or document.get("length") != len(rows)
        or document.get("isHttpError")
        or any(not {"symbol", "name", "instruments"} <= row.keys() for row in rows)
    ):
        raise ValueError("TMX security directory is incomplete or has changed schema")
    for row in rows:
        if any(not {"symbol", "name"} <= item.keys() for item in row["instruments"]):
            raise ValueError("TMX security directory has incomplete instruments")
    stamp = document.get("last_updated")
    if not isinstance(stamp, (int, float)):
        raise ValueError("TMX security directory has no publication timestamp")
    return rows, datetime.fromtimestamp(stamp, timezone.utc).isoformat()


def resolve_tmx_securities(records, directories):
    """Replace roots with exchange-published classes, retaining unmatched roots explicitly."""
    resolved = []
    for exchange in ("tsx", "tsxv"):
        issuers = {item["symbol"]: item for item in directories.get(exchange, [])}
        names = {re.sub(r"[^a-z0-9]", "", item["name"].lower()): item for item in issuers.values()}
        used = set()
        for record in (r for r in records if r["source_id"] == exchange):
            issuer = issuers.get(record["source_symbol"]) or names.get(
                re.sub(r"[^a-z0-9]", "", record["name"].lower())
            )
            if issuer is None:
                resolved.append(record)
                continue
            used.add(issuer["symbol"])
            resolved.extend(_tmx_classes(record, issuer))
        # Include recent listings missing from the monthly issuer publication.
        for issuer in issuers.values():
            if issuer["symbol"] in used:
                continue
            record = {
                "source_id": exchange,
                "name": issuer["name"],
                "currency": "CAD",
                "calendar": "XTSE",
                "exchange": exchange.upper(),
                "sector": "",
                "listing_type": "",
                "product_type": "",
                "is_test": False,
                "is_etf": bool(re.search(r"\bETF\b", issuer["name"], re.I)),
                "issuer_metadata": "absent from monthly workbook",
            }
            resolved.extend(_tmx_classes(record, issuer))
    return resolved


def _tmx_classes(record, issuer):
    suffix = ".TO" if record["source_id"] == "tsx" else ".V"
    return [
        {
            **record,
            "source_symbol": item["symbol"],
            "symbol": item["symbol"].replace(".", "-") + suffix,
            "security_name": item["name"],
            "issuer_root": issuer["symbol"],
            "currency": "USD" if item["symbol"].endswith(".U") else "CAD",
            "symbol_identity": "exchange_security_symbol",
            "symbol_mapping_source": "TMX current company directory",
        }
        for item in issuer["instruments"]
    ]


def _exclusion(record, approved_etfs):
    name = record["name"]
    source = record["source_id"]
    if record["is_test"]:
        return "test_issue"
    if not re.fullmatch(r"[A-Z0-9][A-Z0-9.-]{0,19}", record["symbol"]):
        return "unsupported_symbol_mapping"
    if not record["exchange"]:
        return "unknown_exchange_code"
    if record.get("next_shares"):
        return "nextshares"
    if source in CANADIAN_SOURCES and record["currency"] != "CAD":
        return "canadian_non_cad_listing"
    if record.get("listing_status") == "Delisted":
        return "delisted_in_current_directory"
    if record["is_etf"]:
        return (
            None
            if record["symbol"] in approved_etfs
            else "etf_leverage_classification_not_verified"
        )
    if re.search(r"\b(warrants?|rights|preferred|preference|notes?|ETN|debentures?)\b", name, re.I):
        return "non_common_security"
    if source in CANADIAN_SOURCES:
        if re.search(r"\.(PR|PF|WT|WS|DB|RT|CV|P)(?:\.|$)", record["source_symbol"]):
            return "non_common_security_symbol"
        if source == "cse":
            return None if record["directory_security_type"] == "Equity" else "non_common_security"
        if source == "cboe_ca":
            return (
                None
                if record["directory_security_type"] == "equity"
                and record["directory_security_subtype"] in {"common", "subvtshr"}
                else "non_common_security"
            )
        if record["sector"] in {"ETP", "CDR", "CPC/SPAC", "Closed-End Funds", "CPC"}:
            return "non_common_issuer_category"
        if record["product_type"] not in {"", "Income Trust"} or re.search(
            r"\b(CDR|ETF|fund)\b", name, re.I
        ):
            return "non_common_or_ambiguous_issuer"
        # Explicit trust units are equities; an unresolved issuer root is not a unit symbol.
        if re.search(r"\b(trust|units?)\b", name, re.I) and not record["source_symbol"].endswith(
            ".UN"
        ):
            return "non_common_or_ambiguous_issuer"
    elif not re.search(
        r"\b(common stocks?|common shares?|ordinary shares?|ordinary stocks?|"
        r"american depositary shares?|american depository shares?|american depositary receipts?|"
        r"new york registry shares)\b",
        name,
        re.I,
    ):
        return "common_share_type_not_explicit"
    elif re.search(r"\bunits?\b", name, re.I):
        return "unit_security"
    return None


def build_membership(records, baseline):
    """Deterministic eligibility, with every exclusion retained for coverage reporting."""
    approved = {item["symbol"]: item for item in baseline if item["asset_type"] == "etf"}
    instruments, excluded, seen = [], [], set()
    for record in sorted(records, key=lambda item: (item["symbol"], item["source_id"])):
        reason = _exclusion(record, approved)
        if record["symbol"] in seen:
            reason = "duplicate_provider_symbol"
        if reason:
            excluded.append(
                {
                    "symbol": record["symbol"],
                    "name": record["name"],
                    "source_id": record["source_id"],
                    "reason": reason,
                }
            )
            continue
        seen.add(record["symbol"])
        spec = {
            **record,
            "asset_type": "etf" if record["is_etf"] else "stock",
            "group": record.get("sector") or "unclassified-us-equity",
        }
        if record["is_etf"]:
            spec["group"] = approved[record["symbol"]]["group"]
            spec["etf_eligibility_basis"] = (
                "existing project ETF allowlist; not directory leverage data"
            )
        else:
            spec["security_type"] = (
                "issuer_equity_candidate"
                if record["symbol_identity"] == "issuer_root_requires_provider_verification"
                else "common_ordinary_or_equity_depositary_shares"
            )
        instruments.append(spec)
    return instruments, excluded


def discover_universe(workspace, *, client=None, captured_at=None):
    """Fetch official exchange directories and persist an immutable, dated research snapshot.

    Returns a JSON-serializable manifest; ``instruments`` feeds a research-only
    capture workspace. Never writes config/scanner_universe.json or paper state.
    """
    workspace = Path(workspace)
    moment = (
        datetime.now(timezone.utc) if captured_at is None else datetime.fromisoformat(captured_at)
    )
    if moment.tzinfo is None:
        raise ValueError("Universe capture time must include a timezone")
    moment = moment.astimezone(timezone.utc)
    root = workspace / "data/research/universe"
    baseline_path = workspace / "config/scanner_universe.json"
    baseline = json.loads(baseline_path.read_text("utf-8")) if baseline_path.exists() else []
    owned_client = client is None
    if owned_client:
        client = httpx.Client(
            timeout=30, follow_redirects=True, headers={"User-Agent": "Mozilla/5.0"}
        )
    sources, records, tmx_records = [], [], []
    directories = {"tsx": [], "tsxv": []}
    parsers = {
        "tsx": parse_tmx_workbook,
        "cse": parse_cse_directory,
        "cboe_ca": parse_cboe_canada_directory,
    }

    def capture(source_id, url, parser, suffix):
        response = client.get(url)
        response.raise_for_status()
        content = response.content
        rows, vintage = parser(content)
        digest = _digest(content)
        relative = f"data/research/universe/raw/{source_id}.{digest}{suffix}"
        raw_path = workspace / relative
        raw_path.parent.mkdir(parents=True, exist_ok=True)
        if not raw_path.exists():
            raw_path.write_bytes(content)
        source = {
            "source_id": source_id,
            "url": str(response.url),
            "path": relative,
            "sha256": digest,
            "source_vintage": vintage,
            "observed_rows": len(rows),
        }
        return source, rows

    try:
        for source_id, url in SOURCES.items():
            parser = parsers.get(source_id)
            if parser is None:

                def parser(content, key=source_id):
                    return parse_nasdaq_directory(content, key)

            suffix = ".xlsx" if source_id == "tsx" else ".json" if source_id in parsers else ".txt"
            source, rows = capture(source_id, url, parser, suffix)
            sources.append(source)
            if source_id == "tsx":
                tmx_records = rows
            else:
                records.extend(rows)
        tasks = [
            (exchange, letter) for exchange in directories for letter in (*ascii_uppercase, "0-9")
        ]

        def capture_letter(task):
            exchange, letter = task
            source, rows = capture(
                f"{exchange}_directory_{letter}",
                TMX_DIRECTORY_URL.format(exchange=exchange, letter=letter),
                parse_tmx_directory,
                ".json",
            )
            return exchange, source, rows

        with ThreadPoolExecutor(max_workers=4) as pool:
            for exchange, source, rows in pool.map(capture_letter, tasks):
                sources.append(source)
                directories[exchange].extend(rows)
        records.extend(resolve_tmx_securities(tmx_records, directories))
    finally:
        if owned_client:
            client.close()
    instruments, excluded = build_membership(records, baseline)
    membership_hash = _digest(json.dumps(instruments, sort_keys=True).encode())
    snapshot_id = moment.strftime("%Y%m%dT%H%M%S%fZ") + "-" + membership_hash[:12]
    manifest = {
        "schema_version": 1,
        "snapshot_id": snapshot_id,
        "captured_at": moment.isoformat(),
        "membership_sha256": membership_hash,
        "membership_basis": "current listings at discovery",
        "historical_membership": False,
        "sources": sources,
        "instruments": instruments,
        "observed_count": len(records),
        "source_observed_count": sum(item["observed_rows"] for item in sources),
        "exchange_counts": dict(sorted(Counter(item["exchange"] for item in instruments).items())),
        "identity_counts": dict(
            sorted(Counter(item["symbol_identity"] for item in instruments).items())
        ),
        "eligible_count": len(instruments),
        "counts": dict(
            sorted(
                Counter(f"{item['currency']}_{item['asset_type']}" for item in instruments).items()
            )
        ),
        "exclusion_counts": dict(sorted(Counter(item["reason"] for item in excluded).items())),
        "excluded": excluded,
        "limitations": LIMITATIONS,
        "baseline_etfs_sha256": _digest(
            json.dumps([x for x in baseline if x["asset_type"] == "etf"], sort_keys=True).encode()
        ),
    }
    _write_json(root / "snapshots" / f"{snapshot_id}.json", manifest)
    _write_json(root / "latest.json", {"snapshot_id": snapshot_id})
    return manifest


def load_snapshot(workspace, snapshot_id=None):
    workspace = Path(workspace).resolve()
    root = workspace / "data/research/universe"
    if snapshot_id is None:
        snapshot_id = json.loads((root / "latest.json").read_text("utf-8"))["snapshot_id"]
    if not re.fullmatch(r"[0-9TZ-]+[a-f0-9]{12}", snapshot_id):
        raise ValueError("Invalid research universe snapshot ID")
    manifest = json.loads((root / "snapshots" / f"{snapshot_id}.json").read_text("utf-8"))
    if (
        _digest(json.dumps(manifest["instruments"], sort_keys=True).encode())
        != manifest["membership_sha256"]
    ):
        raise ValueError("Research universe membership changed")
    for source in manifest["sources"]:
        path = (workspace / source["path"]).resolve()
        if not path.is_relative_to(root / "raw") or _digest(path.read_bytes()) != source["sha256"]:
            raise ValueError("Research universe source bytes changed or path is outside raw data")
    return manifest
