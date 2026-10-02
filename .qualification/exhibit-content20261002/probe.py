"""Seeded 8-K exhibit-content probe (exhibit-content20261002). See definition.json.

Run on the owner's workstation:
    probe.py --preflight              # checks only; no request, no write
    probe.py --run                    # one new attempt (refused once any attempt exists)
    probe.py --resume ID [--acknowledge-stop]
    probe.py --reanalyze ID           # recomputes the analysis from saved bytes; writes nothing
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
import os
import re
import sqlite3
import subprocess
import sys
import time
import uuid
from contextlib import contextmanager
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from html.parser import HTMLParser
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, unquote, urljoin, urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parents[1]
DEFINITION = ROOT / "definition.json"
FREEZE = ROOT / "freeze.json"
STUDY = "exhibit-content20261002"

# Reused frozen code, executed only from these exact bytes.
AUDIT = (
    ".qualification/disclosure-timing20261001/audit.py",
    "c4ccaa30053d49be5410067321bbd20971558a8abd157cccff203234da6a57b4",
)
CAPTURE = (
    ".qualification/filing-source20260928/capture.py",
    "962bccbf962d6aff53d3102156f3ad1f50765b66a5373124aa6b9ab0a62c84bb",
)
FEATURES = (
    ".qualification/filing-features20260928/features.py",
    "991260b80547c03c873c0d5bf62c57d86bf3fc1f5c0df0c192a7b4cc1fcc372f",
)
CAPTURE_NAMES = [
    "now",
    "sha",
    "load",
    "CaptureError",
    "Halt",
    "NoRedirect",
    "allowed_url",
    "Cache",
    "Index",
    "archive_base",
    "document_url",
]
S_FLOW = ["current_ni", "prior_ni"]
Q_FLOW = ["q_current_cfo", "q_current_ni", "q_prior_cfo", "q_prior_ni"]
ASSETS = ["prior_fy_assets"]
COMPONENTS = S_FLOW + Q_FLOW + ASSETS
PROJECTED = {
    "accession",
    "status",
    "q_status",
    "fiscal_year",
    "fiscal_period",
    "prior_fy_end",
    "current_ni",
    "prior_ni",
    "prior_fy_assets",
    "current_start",
    "current_end",
    "prior_start",
    "prior_end",
    "q_current_cfo",
    "q_current_ni",
    "q_prior_cfo",
    "q_prior_ni",
    "q_prior_fy_assets",
    "q_current_start",
    "q_current_end",
    "q_prior_start",
    "q_prior_end",
}
CONCEPT = {
    "current_ni": "net_income",
    "prior_ni": "net_income",
    "q_current_ni": "net_income",
    "q_prior_ni": "net_income",
    "q_current_cfo": "operating_cash_flow",
    "q_prior_cfo": "operating_cash_flow",
    "prior_fy_assets": "total_assets",
}
LABELS = {
    "net_income": re.compile(r"\bnet \(?(income|earnings|loss)\b", re.I),
    "operating_cash_flow": re.compile(
        r"\b(net )?cash (flows? )?(provided|generated|used|from)\b"
        r"(?:(?!financing|investing)[^|]){0,40}?"
        r"\b(operating activities|operations)\b|\boperating cash flows?\b",
        re.I,
    ),
    "total_assets": re.compile(r"\btotal assets\b", re.I),
}
EXCLUDED_LABEL = re.compile(
    r"adjusted|non-?gaap|pro forma|\bcore\b|excluding|\bbefore\b|per (basic |diluted )?"
    r"(common )?share|margin|non-?controlling|minority|continuing|discontinued"
    r"|\baverage\b|\bunder\s+(?:management|administration|custody)\b",
    re.I,
)
STATEMENT_IMAGE = {
    "net_income": re.compile(
        r"statements? of\b[^.]{0,40}?\b(income|operations|earnings)|income statements?", re.I
    ),
    "operating_cash_flow": re.compile(
        r"statements? of\b[^.]{0,40}?\bcash flows?|cash flows? statements?", re.I
    ),
    "total_assets": re.compile(
        r"balance sheets?|statements? of\b[^.]{0,20}?\bfinancial (condition|position)", re.I
    ),
}
RELEASE = re.compile(r"(press|news|earnings)[\s\-–—]+release", re.I)  # 'Press-Release' too
UNVERIFIED = {
    "period_unverified",
    "scale_unverified",
    "exhibit_unavailable",
}  # possibly stated: upper bound only


class ProbeError(Exception):
    """Declaration, identity or lifecycle failure: nothing further runs."""


def sha(data):
    return hashlib.sha256(data).hexdigest()


def file_sha(path):
    return sha(Path(path).read_bytes())


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def now():
    return datetime.now(timezone.utc).isoformat()


# ------------------------------------------------------------- reused frozen code


def verified_module(relative, digest, name, repo=REPO):
    data = (repo / relative).read_bytes()
    if sha(data) != digest:
        raise ProbeError("Reused module bytes changed; not executed: " + relative)
    spec = importlib.util.spec_from_file_location(name, repo / relative)
    module = importlib.util.module_from_spec(spec)
    exec(compile(data, str(repo / relative), "exec"), module.__dict__)
    return module


class Frozen:
    """The decision-session audit helpers, the capture's fetch cache and the event clock."""

    def __init__(self, repo=REPO):
        self.audit = verified_module(AUDIT[0], AUDIT[1], "exhibit_probe_audit", repo)
        self.audit.use_locked_tzdata()
        audit = self.audit

        def _save(path, value):
            Path(path).parent.mkdir(parents=True, exist_ok=True)
            audit.write_atomic(
                Path(path), json.dumps(value, allow_nan=False, separators=(",", ":")).encode()
            )

        namespace = {
            "datetime": datetime,
            "timezone": timezone,
            "hashlib": hashlib,
            "json": json,
            "os": os,
            "re": re,
            "time": time,
            "Path": Path,
            "REPO": repo,
            "HTMLParser": HTMLParser,
            "Request": Request,
            "build_opener": build_opener,
            "HTTPRedirectHandler": HTTPRedirectHandler,
            "HTTPError": HTTPError,
            "URLError": URLError,
            "urlparse": urlparse,
            "urljoin": urljoin,
            "parse_qs": parse_qs,
            "_save": _save,
        }
        self.capture = audit.load_verified_definitions(
            repo / CAPTURE[0], CAPTURE[1], CAPTURE_NAMES, namespace
        )
        self.features = verified_module(FEATURES[0], FEATURES[1], "exhibit_probe_clock", repo)

    def session(self, acceptance, filing_date, calendar):
        try:
            clock = self.features.event_clock(acceptance, filing_date, calendar)
        except (TypeError, ValueError):
            return None
        return clock["entry_session"]


# ------------------------------------------------------------- declaration


def declaration_problems(definition_path=DEFINITION, freeze_path=FREEZE, repo=REPO):
    raw = Path(definition_path).read_bytes()
    try:
        frozen = load(freeze_path)
        expected = frozen["definition_sha256"]
    except (OSError, ValueError, KeyError, TypeError):
        return None, sha(raw), ["freeze.json missing or unreadable"]
    if sha(raw) != expected:
        return None, sha(raw), ["Definition bytes differ from the frozen declaration"]
    definition = json.loads(raw)
    problems = []
    if definition.get("study") != STUDY:
        problems.append("Unexpected study")
    for relative, digest in frozen.get("code", {}).items():
        path = repo / relative
        if not path.is_file() or file_sha(path) != digest:
            problems.append("Code changed or missing: " + relative)
    expected_code = {
        AUDIT[0]: AUDIT[1],
        CAPTURE[0]: CAPTURE[1],
        FEATURES[0]: FEATURES[1],
    }
    for relative, digest in expected_code.items():
        if frozen.get("code", {}).get(relative) != digest:
            problems.append("Freeze does not bind reused code: " + relative)
    return definition, sha(raw), problems


def input_problems(repo, definition):
    problems = []
    for relative, digest in definition["inputs"].items():
        path = repo / relative
        if not path.is_file():
            problems.append({"path": relative, "problem": "missing"})
        elif file_sha(path) != digest:
            problems.append({"path": relative, "problem": "sha256_mismatch"})
    return problems


def runtime_problems(frozen, definition):
    import platform

    identity = frozen.audit.runtime_identity()
    problems = []
    if not platform.python_version().startswith(definition["runtime"]["python_version"] + "."):
        problems.append("Python " + platform.python_version() + " is not 3.13")
    if identity["tzdata_package"] != definition["runtime"]["tzdata"]:
        problems.append("tzdata package is " + str(identity["tzdata_package"]))
    return identity, problems


# ------------------------------------------------------------- sample and values


def frame(events):
    return [e for e in events if e["strategy_source_qualified"] and e["status"] == "single_prior"]


def draw_sample(events, size, salt=STUDY):
    def key(event):
        return sha((salt + "|" + event["accession"]).encode())

    return sorted(frame(events), key=key)[:size]


def era(filing_date):
    return "2012-2020" if filing_date[:4] <= "2020" else "2021-2025"


def project_values(frozen, path, accessions):
    """Only PROJECTED fields of the sampled accessions; every other value is skipped unread."""
    text = Path(path).read_text(encoding="utf-8")
    records = frozen.audit.project_json(text, PROJECTED)
    if isinstance(records, dict):
        records = records.get("records", [])
    wanted = set(accessions)
    out = {}
    for record in records:
        if isinstance(record, dict) and record.get("accession") in wanted:
            if record["accession"] in out:
                raise ProbeError("Duplicate qualification record: " + record["accession"])
            out[record["accession"]] = record
    return out


def comparison(record):
    """Per component: value (Decimal), required period, or None when not comparable."""
    if record is None:
        return {name: None for name in COMPONENTS}

    def d(name):
        try:
            return Decimal(str(record[name]))
        except (KeyError, InvalidOperation, TypeError, ValueError):
            return None

    def day_(name):
        try:
            return date.fromisoformat(str(record[name]))
        except (KeyError, TypeError, ValueError):
            return None

    out = {}
    s_ok = record.get("status") == "qualified"
    q_ok = record.get("q_status") == "qualified"
    fy, fp = record.get("fiscal_year"), str(record.get("fiscal_period") or "")
    fiscal = {"year": fy, "quarter": int(fp[1]) if re.fullmatch(r"Q[1-4]", fp) else None}
    ytd = None
    if q_ok and day_("q_current_start") and day_("q_current_end"):
        ytd = round(((day_("q_current_end") - day_("q_current_start")).days + 1) / 30.44)
    ytd_months = ytd or (3 * fiscal["quarter"] if fiscal["quarter"] else None)
    specs = {
        "current_ni": (s_ok, "current_ni", ("duration", 3, "current_end")),
        "prior_ni": (s_ok, "prior_ni", ("duration", 3, "prior_end")),
        "prior_fy_assets": (s_ok, "prior_fy_assets", ("instant", None, "prior_fy_end")),
        "q_current_cfo": (q_ok, "q_current_cfo", ("duration", ytd, "q_current_end")),
        "q_current_ni": (q_ok, "q_current_ni", ("duration", ytd, "q_current_end")),
        "q_prior_cfo": (q_ok, "q_prior_cfo", ("duration", ytd, "q_prior_end")),
        "q_prior_ni": (q_ok, "q_prior_ni", ("duration", ytd, "q_prior_end")),
    }
    for name, (ok, field, (kind, months, end_field)) in specs.items():
        value, end = d(field), day_(end_field)
        if not ok or value is None or end is None or (kind == "duration" and not months):
            out[name] = None
        else:
            out[name] = {
                "value": value,
                "kind": kind,
                "months": months,
                "end": end,
                "ytd_months": ytd_months,
            }
    for name in COMPONENTS:
        if out[name] is not None:
            out[name]["fiscal"] = fiscal
            out[name]["prior"] = name in ("prior_ni", "q_prior_cfo", "q_prior_ni")
    return out


# ------------------------------------------------------------- 8-K index and header


def parse_8k_index(capture, raw, base, accession):
    parser = capture.Index()
    parser.feed(raw.decode("utf-8", errors="replace"))
    text = " ".join(" ".join(parser.text).split())
    found = re.search(r"SEC Accession No\.\s+([0-9-]+)", text)
    if not found or found[1] != accession:
        raise capture.CaptureError("Index accession mismatch")
    docs = []
    for row in parser.rows:
        if len(row) >= 4 and row[2]["links"]:
            docs.append(
                {
                    "description": row[1]["text"],
                    "type": row[3]["text"],
                    "url": capture.document_url(base, row[2]["links"][0]),
                }
            )
    return [d for d in docs if d["type"].upper().startswith("EX-99")]


def header_identity(header, issuer_cik, accession):
    def sgml(name):
        found = re.search("<" + name + r">\s*([^\r\n<]+)", header)
        return found[1].strip() if found else None

    # the filer's CIK only: a subject company or other party in the header is not the filer
    filers = re.findall(r"<FILER>(.*?)(?=</FILER>|<FILER>|$)", header, re.S)
    ciks = [x.zfill(10) for block in filers for x in re.findall(r"<CIK>\s*(\d+)", block)]
    items = [x.strip() for x in re.findall(r"<ITEMS>\s*([^\r\n<]+)", header)]
    issues, missing = [], []  # observed mismatches; absent evidence
    found, form = sgml("ACCESSION-NUMBER"), sgml("TYPE")
    if found is None:
        missing.append("header accession missing")
    elif found != accession:
        issues.append("header accession mismatch")
    if not ciks:
        missing.append("header CIK missing")
    elif issuer_cik not in ciks:
        issues.append("header CIK mismatch")
    if form is None:
        missing.append("header form missing")
    elif form != "8-K":
        issues.append("header form is not 8-K")
    if items and "2.02" not in items:
        issues.append("header items omit 2.02")
    accepted, filed = sgml("ACCEPTANCE-DATETIME"), sgml("FILING-DATE")
    acceptance = filing_date = None
    try:
        zone = ZoneInfo("America/New_York")  # resolved after Frozen() locks tzdata
        stamp = datetime.strptime(accepted, "%Y%m%d%H%M%S").replace(tzinfo=zone)
        acceptance = stamp.isoformat()
        filing_date = datetime.strptime(filed, "%Y%m%d").date().isoformat()
    except (TypeError, ValueError):
        acceptance = filing_date = None
        missing.append("header acceptance or filing date missing")
    return {
        "ciks": ciks,
        "items": items,
        "acceptance": acceptance,
        "filing_date": filing_date,
        "issues": issues,
        "missing": missing,
    }


# ------------------------------------------------------------- release documents


def document_kind(url, raw):
    head = raw[:4096].lower()
    if raw.startswith(b"%PDF") or url.lower().endswith(".pdf"):
        return "unsupported"
    if url.lower().endswith((".htm", ".html")) or b"<html" in head or b"<table" in head:
        return "html"
    if url.lower().endswith(".txt"):
        return "text"
    return "unsupported"


def decode(raw):
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return raw.decode("cp1252", errors="replace")


class Release(HTMLParser):
    """Tables (rows of cells with colspan), text blocks outside tables, and images.
    A nested table is kept as its own table; each table tracks its own open row and cell.
    A table's context is the last two text blocks between it and the previous top-level table."""

    BREAK = {"p", "div", "br", "li", "tr", "h1", "h2", "h3", "h4", "h5", "h6", "table"}

    def __init__(self):
        super().__init__()
        self.tables, self.blocks, self.images = [], [], []
        self.stack, self.text, self.since_table = [], [], []
        self.ordered, self.sup = [], 0  # every text node in source order; <sup> depth
        self.skip = 0  # <script>/<style> depth
        self.tail = ""  # the last text before the current position, in or out of tables

    def _flush(self):
        block = " ".join("".join(self.text).split())
        if block:
            self.blocks.append(block)
            self.since_table.append(block)
        self.text = []

    def context(self):
        """The last two text blocks since the previous top-level table ended."""
        return " ".join(self.since_table[-2:])[-300:]

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self.skip += 1
            return
        if tag == "sup":
            self.sup += 1
            return
        if tag in self.BREAK or tag in ("td", "th"):
            self.sup = 0  # an unclosed <sup> never swallows the following cell or block
            self.ordered.append(" ")
            self.tail += " "
        attrs = dict(attrs)
        top = self.stack[-1] if self.stack else None
        if tag == "table":
            if top is None:
                self._flush()
                context = self.context()
                heading = self.since_table[-1] if self.since_table else ""
            else:  # a nested table also takes the text before it in its enclosing cell
                cell = "".join(top["cell"]["text"]) if top["cell"] is not None else ""
                context = " ".join((top["context"] + " " + cell).split())[-300:]
                heading = " ".join(cell.split())
            self.stack.append(
                {"rows": [], "caption": "", "context": context, "heading": heading}
                | {"row": None, "cell": None}
            )
        elif tag == "tr" and top is not None:
            self._close_row(top)  # an omitted </tr> (and </td>) ends at the next row
            top["row"] = []
        elif tag in ("td", "th") and top is not None:
            self._close_cell(top)  # an omitted </td> ends at the next cell
            if top["row"] is None:
                top["row"] = []  # a cell outside any <tr> opens an implied row
            top["cell"] = {
                "text": [],
                "span": _span(attrs, "colspan"),
                "rows": _span(attrs, "rowspan"),
            }
        elif tag == "img":
            self.images.append(
                {
                    "alt": attrs.get("alt") or "",
                    "src": attrs.get("src") or "",
                    "context": " ".join(self.tail.split())[-300:],
                }
            )
        elif tag in self.BREAK and top is None:
            self._flush()
        elif tag in self.BREAK and top["cell"] is not None:
            top["cell"]["text"].append(" ")  # <br>, <p> or <div> inside a cell

    def handle_endtag(self, tag):
        if tag in ("script", "style"):
            self.skip = max(0, self.skip - 1)
            return
        if tag == "sup":
            self.sup = max(0, self.sup - 1)
            return
        if tag in self.BREAK or tag in ("td", "th"):
            self.sup = 0
            self.ordered.append(" ")
            self.tail += " "
        top = self.stack[-1] if self.stack else None
        if top is None:
            if tag in self.BREAK:
                self._flush()
            return
        if tag in self.BREAK and tag not in ("tr", "table") and top["cell"] is not None:
            top["cell"]["text"].append(" ")
        elif tag in ("td", "th"):
            self._close_cell(top)
        elif tag == "tr":
            self._close_row(top)
        elif tag == "table":
            self._close_row(top)
            table = self.stack.pop()
            self.tables.append({k: table[k] for k in ("rows", "caption", "context", "heading")})
            if not self.stack:
                self.since_table = []

    @staticmethod
    def _close_cell(top):
        if top["cell"] is not None and top["row"] is not None:
            text = " ".join("".join(top["cell"]["text"]).split())
            top["row"].append(
                {"text": text, "span": top["cell"]["span"], "rows": top["cell"]["rows"]}
            )
        top["cell"] = None

    def _close_row(self, top):
        self._close_cell(top)
        if top["row"] is not None:
            top["rows"].append(top["row"])
        top["row"] = None

    def handle_data(self, data):
        if self.skip or self.sup:
            return  # script/style is not shown; superscript markers are not values or labels
        self.ordered.append(data)
        self.tail = (self.tail + data)[-600:]
        top = self.stack[-1] if self.stack else None
        if top is None:
            self.text.append(data)
        elif top["cell"] is not None:
            top["cell"]["text"].append(data)
        elif top["row"] is None:
            top["caption"] += " " + data

    def close(self):
        super().close()
        self._flush()


def _span(attrs, name):
    try:
        return max(1, min(int(attrs.get(name) or 1), 50))
    except ValueError:
        return 1


def parse_document(kind, raw):
    text = decode(raw)
    if kind == "text":
        tables, blocks = text_tables(text)
        return {"tables": tables, "blocks": blocks, "images": [], "text": text}
    parser = Release()
    parser.feed(text)
    parser.close()
    return {
        "tables": parser.tables,
        "blocks": parser.blocks,
        "images": parser.images,
        "text": " ".join("".join(parser.ordered).split()),  # source order
    }


TEXT_CELL = re.compile(r"\S+(?: \S+)*")
TEXT_RULE = re.compile(r"[\s\-=_]+")


def text_tables(text):
    """Plain text: cells keep their character offsets, so headers align by position.

    A run of data lines forms one table. Walking up from its first data line, a line with a cell
    starting right of that line's label is a header line, a line ending before its first value
    (a section label) is skipped, and any other line ends the header. Inside a table a line with a
    cell right of the label ends it. The other non-data lines since the previous data line are the
    table's context. Rule lines are skipped; non-data lines also form blocks.
    """
    tables, blocks, paragraph, recent, table = [], [], [], [], None

    def flush():
        if paragraph:
            blocks.append(" ".join(paragraph))
            paragraph.clear()

    for line in text.expandtabs(8).splitlines():
        if not line.strip():
            flush()
            continue
        if TEXT_RULE.fullmatch(line):
            continue
        cells = [
            {"text": m[0], "col": m.start(), "span": len(m[0])} for m in TEXT_CELL.finditer(line)
        ]
        if is_data_row([c["text"] for c in cells]):
            flush()
            if table is None:
                label_end = cells[0]["col"] + cells[0]["span"]
                header, index = [], len(recent) - 1
                while index >= 0:
                    above = recent[index]
                    if any(c["col"] >= label_end for c in above):
                        header.insert(0, above)
                    elif any(c["col"] + c["span"] > cells[1]["col"] for c in above):
                        break
                    index -= 1
                context = " ".join(
                    " ".join(c["text"] for c in above)
                    for above in recent
                    if not any(above is h for h in header)
                )
                above = [r for r in recent if not any(r is h for h in header)]
                heading = " ".join(c["text"] for c in above[-1]) if above else ""
                table = {"rows": header, "context": context[-300:], "label_end": label_end}
                table["heading"] = heading
                tables.append(table)
            table["rows"].append(cells)
            recent = []
            continue
        if table is not None and any(c["col"] >= table["label_end"] for c in cells):
            table = None
        recent.append(cells)
        paragraph.append(" ".join(c["text"] for c in cells))
    flush()
    return [
        {"rows": t["rows"], "caption": "", "context": t["context"], "heading": t["heading"]}
        | {"text": True}
        for t in tables
    ], blocks


# ------------------------------------------------------------- numbers and periods

MONTHS = {
    m: i + 1
    for i, names in enumerate(
        [
            "jan january",
            "feb february",
            "mar march",
            "apr april",
            "may",
            "jun june",
            "jul july",
            "aug august",
            "sep sept september",
            "oct october",
            "nov november",
            "dec december",
        ]
    )
    for m in names.split()
}
MONTH = r"(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|june?|july?|aug(?:ust)?|"
MONTH += r"sept?(?:ember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\.?"
DATE_MDY = re.compile(MONTH + r"\s+(\d{1,2}),?\s*((?:19|20)\d{2})", re.I)
DATE_MD = re.compile(MONTH + r"\s+(\d{1,2})\b", re.I)
DATE_MY = re.compile(MONTH + r",?\s+((?:19|20)\d{2})\b", re.I)
YEAR = re.compile(r"\b((?:19|20)\d{2})\b")
DURATIONS = [
    (3, r"\b(three|3)[- ]months?\b|\bquarters?\b|\b1[2-4][- ]weeks?\b|\bq[1-4]\b"),
    (6, r"\b(six|6)[- ]months?\b|\b2[5-7][- ]weeks?\b|\bfirst half\b|\bhalf[- ]year\b"),
    (9, r"\b(nine|9)[- ]months?\b|\b3[89][- ]weeks?\b|\b40[- ]weeks?\b"),
    # 'of fiscal year 2025' names the year a quarter belongs to, not a twelve-month period
    (12, r"\b(twelve|12)[- ]months?\b|(?<!of )\bfiscal year\b|\byear ended\b|\b5[1-3][- ]weeks?\b"),
]
SHARED_MONTHS = re.compile(
    r"\b(three|six|nine|twelve|3|6|9|12)\s+and\s+(?=(?:three|six|nine|twelve|3|6|9|12)[- ]months?)",
    re.I,
)
YTD = re.compile(r"\byear[- ]to[- ]date\b|\bytd\b", re.I)
SCALE_WORDS = [
    (Decimal(10**9), re.compile(r"\bbillions?\b", re.I)),
    (Decimal(10**6), re.compile(r"\bmillions?\b", re.I)),
    (Decimal(10**3), re.compile(r"\bthousands?\b|\(000'?s\)|\$000", re.I)),
]
OTHER_CODES = (
    "CAD|AUD|EUR|GBP|JPY|CHF|CNY|RMB|HKD|SGD|INR|KRW|BRL|MXN|SEK|NOK|DKK|NZD|ZAR|ILS|TWD|PLN"
)
OTHER_SIGNS = "€|£|¥|₹|₩|₪"
OTHER_NAMES = (  # currency names that mark a non-USD amount
    r"(?:canadian|australian|hong\s+kong|new\s+zealand|singapore|taiwan(?:ese)?)\s+dollars?"
    r"|euros?|pounds?\s+sterling|(?:japanese\s+)?yen|(?:chinese\s+)?(?:yuan|renminbi)"
    r"|(?:swiss\s+)?francs?|swedish\s+kron(?:a|or)|(?:norwegian|danish)\s+kron(?:e|er)"
    r"|(?:indian\s+)?rupees?|korean\s+won|brazilian\s+reais?|(?:mexican\s+)?pesos?"
    r"|south\s+african\s+rand|(?:israeli\s+)?shekels?|(?:polish\s+)?zloty"
)
OTHER_CURRENCY = re.compile(r"(?!US\$)\b[A-Z]{1,3}\$|\b(?:" + OTHER_CODES + r")\b|" + OTHER_SIGNS)
NUMBER = re.compile(r"^(\d{1,3}(?:,\d{3})+|\d+)(\.\d+)?$")
PREFIX_CELL = re.compile(
    r"\(?\s*([A-Z]{1,3}\$|\$|" + OTHER_SIGNS + "|USD|" + OTHER_CODES + r")?\s*\(?"
)
CODE_CELL = re.compile(
    "USD|" + OTHER_CODES + "|" + OTHER_SIGNS + r"|(?<![A-Z])(?!US\$)[A-Z]{1,3}\$"
)
CELL_SCALE = re.compile(r"\s*\b(thousands?|millions?|billions?)\b\.?", re.I)  # '$5.2 million'
CONTEXT_CURRENCY = re.compile(  # a unit phrase that names another currency, e.g. in a caption
    r"(?:thousands|millions|billions)\s+of\s+(?:" + OTHER_NAMES + r"|pounds"
    r"|(?-i:(?!US\$)\b[A-Z]{1,3}\$)|\b(?:" + OTHER_CODES + r")\b)"
    # the currency named first: 'CAD in thousands', 'Canadian dollars in millions'
    r"|(?:\b(?:"
    + OTHER_CODES
    + r")\b|(?-i:(?!US\$)\b[A-Z]{1,3}\$)|"
    + OTHER_SIGNS
    + r"|\b(?:"
    + OTHER_NAMES
    + r"))"
    r"\s*,?\s*\(?\s*(?:in\s+)?(?:thousands|millions|billions|000s?)\b",
    re.I,
)
CURRENCY_NAME = (
    r"(?:\b(?:"
    + OTHER_NAMES
    + r")|\b(?:"
    + OTHER_CODES
    + r")\b|"
    + OTHER_SIGNS
    + r"|(?-i:(?!US\$)\b[A-Z]{1,3}\$))"
)
DECLARED_CURRENCY = re.compile(  # 'All amounts are in CAD.', '(in millions) CAD', '(C$)'
    r"\b(?:expressed|stated|presented|reported|denominated)\s+in\s+"
    + CURRENCY_NAME
    + r"|\b(?:amounts?|figures)\b[^.;]{0,30}?\b(?:are|is)\s+(?:\w+\s+)?in\s+"
    + CURRENCY_NAME
    + r"|\(\s*(?:in\s+)?"
    + CURRENCY_NAME
    + r"\s*\)"
    + r"|\(\s*in\s+(?:thousands|millions|billions)[^)]{0,40}\)\s*"
    + CURRENCY_NAME,
    re.I,
)
OTHER_CURRENCY_WORDS = re.compile(
    r"(?-i:(?!US\$)\b[A-Z]{1,3}\$)|\b(?:"
    + OTHER_CODES
    + r")\b|"
    + OTHER_SIGNS
    + r"|\b(?:"
    + OTHER_NAMES
    + r")\b",
    re.I,
)


def parse_number(text):
    """(value, decimals, currency) for a numeric cell, or None. Currency is 'USD', 'other' or ''."""
    t = text.strip()
    t = re.sub(r"(?<=[\d)])\s*\(\d{1,2}\)$", "", t)  # '5.2(1)': a numbered footnote
    t = re.sub(r"(\s*(\*+|\([a-z]\)|\[\d+\]))+$", "", t)
    if not t or "%" in t:
        return None
    if OTHER_CURRENCY.search(t):
        currency = "other"
        t = OTHER_CURRENCY.sub("", t)
    elif re.search(r"US\$|\$|\bUSD\b", t):
        currency = "USD"
        t = re.sub(r"US\$|\$|\bUSD\b", "", t)
    else:
        currency = ""
    t = t.replace("−", "-").replace("–", "-").strip()
    if t in ("-", "—", "--"):
        return Decimal(0), 0, currency
    negative = t.startswith("(") or t.startswith("-")
    t = t.strip("()- ").strip()
    match = NUMBER.match(t)
    if not match:
        return None
    digits = match[1].replace(",", "") + (match[2] or "")
    value = Decimal(digits)
    return (-value if negative else value), len(match[2] or "") - (1 if match[2] else 0), currency


def is_year(text):
    return bool(re.fullmatch(r"\s*(19[9]\d|20[0-3]\d)\s*", text))


def durations(s):
    """The distinct durations (in months) named in s; 'three and six months' names both."""
    s = SHARED_MONTHS.sub(r"\1 months and ", s)
    return {m for m, pattern in DURATIONS if re.search(pattern, s, re.I)}


def parse_period(text, context=""):
    """{'months', 'end', 'instant', 'ytd'} from header text, using context only to fill gaps."""

    found = durations(text)
    ytd = bool(YTD.search(text))
    dates = {
        date(int(y), MONTHS[m.lower().rstrip(".")[:3]], int(d))
        for m, d, y in DATE_MDY.findall(text)
        if _valid(int(y), MONTHS[m.lower().rstrip(".")[:3]], int(d))
    }
    if dates:  # another date form beside a full date ('June 30, 2025 and March 2025') adds one
        years = {(MONTHS[m.lower().rstrip(".")[:3]], int(y)) for m, y in DATE_MY.findall(text)}
        days = {(MONTHS[m.lower().rstrip(".")[:3]], int(d)) for m, d in DATE_MD.findall(text)}
        years -= {(d.month, d.year) for d in dates}
        days -= {(d.month, d.day) for d in dates}
        dates |= {("other", m, n) for m, n in years | days}
    if not dates:  # month-year: the last day of that month
        dates = {
            _month_end(int(y), MONTHS[m.lower().rstrip(".")[:3]]) for m, y in DATE_MY.findall(text)
        }
    if not dates:
        years = set(YEAR.findall(text))
        month_days = DATE_MD.findall(text) or DATE_MD.findall(context)
        month_days = {(MONTHS[m.lower().rstrip(".")[:3]], int(d)) for m, d in month_days}
        if len(years) == 1 and len(month_days) == 1:
            (month, day_), year = month_days.pop(), int(years.pop())
            if _valid(year, month, day_):
                dates = {date(year, month, day_)}
    if not found and not ytd and dates:
        found = durations(context)
        ytd = bool(YTD.search(context)) and not found
    months = next(iter(found)) if len(found) == 1 else None
    end = dates.pop() if len(dates) == 1 else None  # several dates: no single end
    instant = end is not None and not found and not ytd
    return {"months": months, "end": end, "instant": instant, "ytd": ytd}


def _month_end(year, month):
    following = date(year + month // 12, month % 12 + 1, 1)
    return date.fromordinal(following.toordinal() - 1)


def _valid(year, month, day_):
    try:
        date(year, month, day_)
    except ValueError:
        return False
    return True


def period_months(period, spec):
    """Parsed duration; a bare year-to-date header takes the 10-Q's year-to-date length."""
    if period["months"] is None and period["ytd"]:
        return spec.get("ytd_months")
    return period["months"]


def period_ok(period, spec):
    if period["end"] is None or abs((period["end"] - spec["end"]).days) > 7:
        return False
    if spec["kind"] == "instant":
        return period["instant"]
    return not period["instant"] and period_months(period, spec) == spec["months"]


UNIT_PHRASES = [
    (
        Decimal(10**9),
        re.compile(r"\bin\s+billions\b|\bbillions\s+of\s+(u\.?s\.?\s+)?dollars\b", re.I),
    ),
    (
        Decimal(10**6),
        re.compile(r"\bin\s+millions\b|\bmillions\s+of\s+(u\.?s\.?\s+)?dollars\b", re.I),
    ),
    (
        Decimal(10**3),
        re.compile(
            r"\bin\s+thousands\b|\bthousands\s+of\s+(u\.?s\.?\s+)?dollars\b|\(000'?s?\)|\$\s?000\b",
            re.I,
        ),
    ),
]


def unit_scale(texts):
    """Scale options from the nearest text naming a unit ('in millions', '$000'); a level naming
    several units, or none at all, leaves every scale possible."""
    for text in texts:
        found = [scale for scale, pattern in UNIT_PHRASES if pattern.search(text or "")]
        if len(found) == 1:
            return found
        if found:
            break
    return [Decimal(1), Decimal(10**3), Decimal(10**6), Decimal(10**9)]


def scales(text):
    for scale, pattern in SCALE_WORDS:
        if pattern.search(text):
            return [scale]
    return [Decimal(1), Decimal(10**3), Decimal(10**6), Decimal(10**9)]


def equal(number, decimals, scale_options, value, negative_label=False):
    """The scale at which the displayed number equals value; under a loss or cash-used label an
    unsigned number is negative."""
    if negative_label and number > 0:
        number = -number
    for scale in scale_options:
        tolerance = Decimal("0.5") * Decimal(10) ** (-decimals) * scale
        if abs(number * scale - value) <= tolerance:
            return scale
    return None


# ------------------------------------------------------------- matching


def is_data_row(texts):
    """A label followed by at least one number that is not a year."""
    texts = [t for t in texts if t]
    return len(texts) >= 2 and any(
        parse_number(CELL_SCALE.sub("", t)) is not None and not is_year(t) for t in texts[1:]
    )


def label_match(text, concept):
    found = LABELS[concept].search(text)
    if not found or EXCLUDED_LABEL.search(text):
        return None
    return found[0]


def grid(rows):
    """Expand colspan and rowspan so every cell has a column index. A cell spanning rows is
    repeated in the rows below at its column; plain-text cells carry their character offset."""
    out, carry = [], {}
    for row in rows:
        cells, column, born = [], 0, {}

        def carried():
            nonlocal column
            while column in carry:
                cell = carry[column][0]
                cells.append({"text": cell["text"], "col": column, "span": cell["span"]})
                column += cell["span"]

        for cell in row:
            if "col" in cell:
                column = cell["col"]
            else:
                carried()
            cells.append({"text": cell["text"], "col": column, "span": cell["span"]})
            if cell.get("rows", 1) > 1:
                born[column] = [cell, cell["rows"] - 1]
            column += cell["span"]
        carried()
        carry = {k: [c, left - 1] for k, (c, left) in carry.items() if left > 1}
        carry.update(born)
        out.append(cells)
    return out


def is_period_row(cells):
    """A non-data row naming a year, date, duration or year to date beyond its first cell, or in
    a single filled cell that spans several columns (a full-row section header)."""
    filled = [c for c in cells if c["text"]]
    if len(filled) == 1 and filled[0]["span"] > 1:
        text = filled[0]["text"]
    else:
        text = " ".join(c["text"] for c in cells[1:])
    return bool(
        YEAR.search(text)
        or DATE_MD.search(text)
        or YTD.search(text)
        or any(re.search(pattern, text, re.I) for _, pattern in DURATIONS)
    )


def _merge(filled):
    """Join currency marks, codes, parentheses and percent signs to the value cells they mark.

    A currency code in its own cell is read by the row's layout: a code before the first value
    makes codes prefixes, a code after the last value makes them suffixes, and a code only
    between two values marks both, so a foreign code never leaves a value unmarked."""
    cells = filled[1:]
    values = [
        i
        for i, c in enumerate(cells)
        if not PREFIX_CELL.fullmatch(c["text"]) and c["text"] not in (")", ")%", "%")
    ]

    def coded(part):
        return any(PREFIX_CELL.fullmatch(c["text"]) and CODE_CELL.search(c["text"]) for c in part)

    leading = bool(values) and coded(cells[: values[0]])
    trailing = bool(values) and coded(cells[values[-1] + 1 :])
    merged, prefix = [], ""
    for c in cells:
        text = c["text"]
        if PREFIX_CELL.fullmatch(text):
            code = CODE_CELL.search(text)
            if code and merged and not leading:  # a code after a value may be its suffix
                merged[-1]["text"] += " " + code[0]
                if trailing:  # suffix layout: it is not also the next value's prefix
                    text = text.replace(code[0], "", 1)
            prefix += text
            continue
        if merged and (text in (")", ")%", "%") or CODE_CELL.fullmatch(text)):
            merged[-1]["text"] += (" " + text) if text[0].isalpha() else text
            continue
        joined = prefix + (" " if prefix[-1:].isalpha() else "") + text
        merged.append({"text": joined, "col": c["col"], "span": c["span"]})
        prefix = ""
    if merged and leading and CODE_CELL.search(prefix):  # a trailing code marks the last value
        merged[-1]["text"] += " " + prefix.strip()
    return merged


def value_columns(rows):
    """(column, span) of every merged value in the data rows of a gridded table."""
    return [
        (m["col"], m["span"])
        for cells in rows
        if is_data_row([c["text"] for c in cells])
        for m in _merge([c for c in cells if c["text"]])
    ]


def table_cells(table):
    """Yield (label, value text, column header, table-wide context, row, unit texts, table-wide
    currency text) per value.

    The header is the rows above the first data row. After a data row, a period row starts a new
    header block (a stacked section such as 'Six Months Ended') for the rows below it. A value's
    column header is the header cells overlapping its columns. The table-wide context is the
    caption and preceding text, header cells that overlap no value column (such as '(in
    thousands)' above the labels), and header rows with a single filled cell outside the label
    column; another column's header never supplies a value's period or scale.
    """
    rows = grid(table["rows"])
    context = " ".join([table.get("caption", ""), table.get("context", "")])
    values = value_columns(rows)
    header, fresh = [], True
    tolerance = 6 if table.get("text") else 0  # plain-text headers sit near, not over, values

    def overlaps(c, column, span):
        return c["col"] < column + span and column < c["col"] + c["span"]

    def column_header(column, span):
        """Per header row, the cell overlapping the value most, else (plain text) the nearest
        cell within the tolerance; one cell per row, so a neighbour's header is never borrowed."""
        parts = []
        for cells in header:
            best, key = None, None
            for c in cells:
                if not c["text"]:
                    continue
                overlap = min(c["col"] + c["span"], column + span) - max(c["col"], column)
                if overlap <= -tolerance or (overlap <= 0 and not tolerance):
                    continue
                if key is None or overlap > key:
                    best, key = c, overlap
            if best is not None:
                parts.append(best["text"])
        return " ".join(parts)

    def header_wide():
        """Table-wide header text, and the part of it that may name every value's currency."""
        parts, currency = [], []
        for cells in header:
            filled = [c for c in cells if c["text"]]
            over = [c for c in filled if any(overlaps(c, col, span) for col, span in values)]
            parts += [c["text"] for c in filled if c not in over]  # e.g. '(in thousands)'
            currency += [c["text"] for c in filled if c not in over]
            if len(over) == 1:  # a single header over the values: its period and scale are
                parts.append(over[0]["text"])  # shared ('Three Months Ended' over the first)
                if all(overlaps(over[0], col, span) for col, span in values):
                    currency.append(over[0]["text"])  # a currency only when it spans them all
        return " ".join(parts), " ".join(currency)

    for row, cells in enumerate(rows):
        if not is_data_row([c["text"] for c in cells]):
            if fresh:
                header.append(cells)
            elif is_period_row(cells):
                header, fresh = [cells], True
            continue
        fresh = False
        filled = [c for c in cells if c["text"]]
        wide, currency = header_wide()
        for m in _merge(filled):
            column = column_header(m["col"], m["span"])
            units = [column, wide, table.get("caption", ""), table.get("context", "")]
            yield filled[0]["text"], m["text"], column, context + " " + wide, row, units, currency


ABBREVIATIONS = (
    "Jan Feb Mar Apr Jun Jul Aug Sep Sept Oct Nov Dec Inc Corp Co Ltd LLC vs No Nos approx"
    " Mr Ms Mrs Dr St Jr Sr U.S U.K e.g i.e etc"
).split()
CLOSING = "[\"'”’)]"
TAILS = ("", CLOSING, CLOSING * 2)  # up to two closing quotes or brackets after the punctuation
SENTENCE_BREAK = re.compile(
    "(?:"
    + "|".join(r"(?<=[.;!?]" + tail + ")" for tail in TAILS)
    + ")"
    + "".join(
        r"(?<!\b" + word + r"\." + tail + ")"
        for word in [re.escape(a) for a in ABBREVIATIONS] + ["[A-Z]"]  # '[A-Z]': an initial
        for tail in TAILS
    )
    + r"\s+(?=[\"'“‘(]?[A-Za-z0-9$])",
    re.I,
)


def sentences(blocks):
    """Split at sentence ends, including after closing quotes and before quotes, digits and
    lowercase starts, but never after an abbreviation such as 'Sept.' or 'Inc.' or an initial."""
    for block in blocks:
        for sentence in SENTENCE_BREAK.split(block):
            if sentence:
                yield sentence


AMOUNT = (  # '5.2 million', '(5.2) million' after a currency mark
    r"(?P<int>\d{1,3}(?:,\d{3})+|\d+)(?P<frac>\.\d+)?\)?"
    r"(?:\s*(?P<word>thousand|million|billion))?"
)
MONEY_BEFORE = re.compile(
    r"(?P<neg>\(|[-−]\s?)?(?<![a-z])(?P<cur>(?-i:[A-Z]{1,3})?\$|"
    + OTHER_SIGNS
    + r"|\b(?:USD|"
    + OTHER_CODES
    + r")\s?)"
    r"\s?(?P<neg2>[-−]|\(\s?)?" + AMOUNT,
    re.I,
)
MONEY_AFTER = re.compile(
    r"(?P<neg>\(\s?|[-−])?" + AMOUNT + r"\s+(?P<cur>USD|" + OTHER_CODES + r")\b", re.I
)
USD_MARKS = {"$", "US$", "USD"}
TRAILING_CURRENCY = re.compile(  # '$5.2 million CAD': the code after the amount names it
    r"\s*(?:\b(?P<code>USD|" + OTHER_CODES + r")\b|(?P<name>" + OTHER_NAMES + r")\b)", re.I
)


def money_amounts(clause):
    """Currency amounts in source order: (text, value, decimals, scale word, is_usd, offset)."""
    found = list(MONEY_BEFORE.finditer(clause))
    spans = [f.span() for f in found]
    found += [
        f
        for f in MONEY_AFTER.finditer(clause)
        if not any(a < f.end() and f.start() < b for a, b in spans)
    ]
    out = []
    for f in sorted(found, key=lambda f: f.start()):
        value = Decimal(f["int"].replace(",", "") + (f["frac"] or ""))
        if f["neg"] or f.groupdict().get("neg2"):
            value = -value
        decimals = len(f["frac"] or "") - (1 if f["frac"] else 0)
        currency = f["cur"].strip().upper()
        usd = currency in USD_MARKS
        after = TRAILING_CURRENCY.match(clause, f.end())
        if after and (after["name"] or after["code"].upper() != "USD"):
            usd = False
        out.append((f[0], value, decimals, (f["word"] or "").lower(), usd, f.start()))
    return out


# a spelled-out ordinal counts only before 'quarter' ('first and second quarters' included)
QUARTER_WORD = (
    r"(?:first|second|third|fourth)(?=(?:\s*(?:,|and|or|through|to)\s*(?:the\s+)?"
    r"(?:first|second|third|fourth))*\s+(?:fiscal\s+)?quarters?\b)"
)
QUARTER_LIST = re.compile(  # 'first and second quarters', 'Q1 and Q2': several quarters at once
    r"\b(?:first|second|third|fourth)(?:\s*(?:,|and|or|through|to)\s*(?:the\s+)?"
    r"(?:first|second|third|fourth))+\s+(?:fiscal\s+)?quarters?\b"
    r"|\bq[1-4](?:\s*(?:,|and|or|through|to|-|–)\s*q[1-4])+\b",
    re.I,
)
FISCAL_QUARTER = re.compile(  # 'second quarter of fiscal 2025', 'Q2 FY2025', 'FY25 Q2'
    r"\b(?P<qa>" + QUARTER_WORD + r"|q[1-4])\b[^.;]{0,25}?"
    r"(?:\bfy\s*'?(?P<ya2>\d{2})\b|\b(?:fiscal\s+|fy\s*'?)?(?P<ya>(?:19|20)\d{2})\b)"
    r"|\b(?:fiscal\s+(?P<yb>(?:19|20)\d{2})|fy\s*'?(?P<yb2>(?:19|20)?\d{2}))\s+"
    r"(?P<qb>" + QUARTER_WORD + r"|q[1-4])\b",
    re.I,
)
ORDINAL = {"first": 1, "second": 2, "third": 3, "fourth": 4, "q1": 1, "q2": 2, "q3": 3, "q4": 4}


OTHER_METRIC = re.compile(  # a different measure named between a label and an amount
    r"\b(ebitda|ebit|revenues?|sales|operating (income|loss)|income from operations"
    r"|gross (profit|margin)|margins?|earnings per|per (basic |diluted )?share|eps"
    r"|free cash flow|cash and cash equivalents|bookings|backlog|adjusted|non-?gaap|guidance"
    r"|outlook|total assets|capital expenditures|investing activities|financing activities)\b",
    re.I,
)
QUALIFIER = re.compile(  # a non-GAAP or partial measure named after an amount or over a column
    r"adjusted|non-?gaap|pro forma|excluding|\bbefore\s+(?:income\s+)?tax"
    r"|non-?controlling|minority|(?:continuing|discontinued)\s+operations",
    re.I,
)
TRAIL_END = re.compile(r"\b(?:and|while|whereas|but)\b", re.I)
PROSPECTIVE = re.compile(  # a forecast is not a disclosure of the actual value
    r"\b(?:forecast(?:s|ed|ing)?|project(?:ed|ing|ions?)|expect(?:s|ed|ing)?"
    r"|anticipat(?:e|es|ed|ing)|estimat(?:e|es|ed|ing)|(?:will|would|could|may|should)\s+be)\b",
    re.I,
)
PER_SHARE_UNIT = re.compile(  # '(in thousands, except per share data)' is a unit line
    r"except\s+(?:for\s+)?per[- ]share\s+(?:data|amounts?|information|figures)", re.I
)


def excluded_header(text):
    """A column or table-wide header naming an excluded measure ('Core', 'Per Share')."""
    return bool(EXCLUDED_LABEL.search(PER_SHARE_UNIT.sub("", text)))


PREFIX_BREAK = re.compile(r"[,;:]|\b(?:and|or|while|whereas|but)\b", re.I)
FORWARD = re.compile(PROSPECTIVE.pattern + r"|\b(?:guidance|outlook)\b", re.I)
NEW_SUBJECT = re.compile(  # 'and income tax expense was': another measure takes the amount
    r"(?:[,;]|\b(?:and|while|whereas|but)\b)\s*(?:(?:the|its|our)\s+)?"
    r"(?!(?:it|this|that|which|they|these|those|in|for|during|at|on|of|from|to|by|with|was|were"
    r"|is|are|and|or|while|whereas|but)\b)\b(?P<subject>[a-z][\w&'\-]*(?:\s+[a-z][\w&'\-]*){0,5})"
    r"(?:\s+(?:was|were|is|are|of|totaled|totalled|amounted\s+to|reached"
    r"|(?:increased|decreased|rose|fell|grew|declined|improved|dropped|climbed)(?:\s+(?:to|by))?)"
    r"\s+|\s*:\s*)"
    r"(?:(?:approximately|about|roughly)\s+)?$",
    re.I,
)
PERIOD_WORD = re.compile(  # 'and first six months were' names a period, not a measure
    r"\b(?:months?|quarters?|years?|weeks?|periods?|half|fiscal|ytd|year-to-date|ended|ending)\b",
    re.I,
)


def new_subject(gap):
    found = NEW_SUBJECT.search(gap)
    return bool(found) and not PERIOD_WORD.search(found["subject"])


CLAUSE = re.compile(
    r";|,?\s+(?:as\s+)?compared\s+(?:with|to)\s+|\s+versus\s+|\s+vs\.?\s+"
    r"|,\s+(?:and|while|whereas|up|down)\s+",
    re.I,
)


def negative_label(text):
    """A label naming only a loss or a use of cash: an unsigned amount under it is negative."""
    t = text.lower()
    loss = "loss" in t and not re.search(r"income|earnings|profit", t)
    used = re.search(r"\bused\b", t) and not re.search(r"provided|generated", t)
    return bool(loss or used)


def _fiscal_year(found):
    year = found["ya"] or found["ya2"] or found["yb"] or found["yb2"]
    return int(year) if len(year) == 4 else 2000 + int(year)  # 'FY25': the filings are 2012-2025


def fiscal_quarters(clause):
    return [
        (ORDINAL.get((f["qa"] or f["qb"]).lower()), _fiscal_year(f))
        for f in FISCAL_QUARTER.finditer(clause)
    ]


def clause_dates(clause):
    """How many distinct dates a clause names in any form parse_period reads: a month, day and
    year, a month and day, or a month and year; a shorter form inside a fuller date is not
    counted again."""

    def month(name):
        return MONTHS[name.lower().rstrip(".")[:3]]

    full = {(month(m), int(d), int(y)) for m, d, y in DATE_MDY.findall(clause)}
    days = {(month(m), int(d)) for m, d in DATE_MD.findall(clause)}
    years = {(month(m), int(y)) for m, y in DATE_MY.findall(clause)}
    days -= {(m, d) for m, d, _ in full}
    years -= {(m, y) for m, _, y in full}
    return len(full) + len(days) + len(years)


QUARTER_ENDED = re.compile(r"[^.;]{0,15}?\bend(?:ed|ing)\s+" + DATE_MDY.pattern, re.I)


def clause_result(clause, spec, amounts):
    """stated, different_period or period_unverified for an equal amount in one clause.

    Several amounts with several periods in one clause (several dates, fiscal quarters, distinct
    years as in 'June 30, 2025 and 2024', or durations as in 'second quarter and first six
    months') cannot be paired, and a clause naming several durations cannot verify one amount;
    both are period_unverified."""
    parsed, quarters = parse_period(clause), fiscal_quarters(clause)
    named = durations(clause)
    # 'second quarter of fiscal 2025 ended June 30, 2025' describes one period, not two
    separate = [
        f for f in FISCAL_QUARTER.finditer(clause) if not QUARTER_ENDED.match(clause, f.end())
    ]
    periods = max(
        len(set(DATE_MDY.findall(clause))) + len(separate),
        len(set(YEAR.findall(clause))),
        len(named),
    )
    # every quarter phrase counts here, including one followed by its own end date
    several = len(named) > 1 or len(set(quarters)) > 1 or bool(QUARTER_LIST.search(clause))
    several = several or clause_dates(clause) > 1
    if (amounts > 1 and periods > 1) or several:
        return "period_unverified"
    fiscal = spec.get("fiscal") or {}
    quarter_ok = False
    if spec["kind"] == "duration" and spec["months"] == 3 and fiscal.get("quarter"):
        try:
            year = int(fiscal["year"]) - (1 if spec.get("prior") else 0)
        except (TypeError, ValueError):
            year = None
        quarter_ok = (fiscal["quarter"], year) in quarters
        quarter_ok = quarter_ok and _period_result(parsed, spec) != "different_period"
    if period_ok(parsed, spec) or quarter_ok:
        return "stated"
    if quarters or _period_result(parsed, spec) == "different_period":
        return "different_period"
    return "period_unverified"


CONTINUES = re.compile(  # a label cell whose sentence runs on into the value cell
    r"\b(?:was|were|is|are|of|totaled|totalled|amounted\s+to|reached|to|approximately)\s*:?$",
    re.I,
)


def match_component(doc, spec, concept):
    """Classify one component in one parsed document, with evidence."""
    label_seen, evidence = False, []
    best = None

    def note(kind, item):
        nonlocal best
        rank = ["stated", "period_unverified", "scale_unverified", "currency_mismatch"]
        evidence.append(dict(item, result=kind))
        if kind in rank and (best is None or rank.index(kind) < rank.index(best)):
            best = kind

    for index, table in enumerate(doc["tables"]):
        table_wide = " ".join([table.get("caption", ""), table.get("context", "")])
        single = len({col for col, _ in value_columns(grid(table["rows"]))}) == 1
        heading = table.get("heading", "")  # the text block just before the table, if short
        title = " ".join([table.get("caption", ""), heading if len(heading) <= 150 else ""])
        for label, cell, header, context, row, units, wide_currency in table_cells(table):
            matched = label_match(label, concept)
            if not matched:
                continue
            label_seen = True
            if any(FORWARD.search(t) for t in (label, header, units[1], title)) or QUALIFIER.search(
                title
            ):
                continue  # 'Estimated net income', an 'Outlook' column, 'Projected Results' title
            unit = CELL_SCALE.search(cell)
            parsed = parse_number(CELL_SCALE.sub("", cell) if unit else cell)
            if parsed is None:
                continue
            number, decimals, currency = parsed
            negative = negative_label(label)
            options = scales(unit[0]) if unit else unit_scale(units)
            scale = equal(number, decimals, options, spec["value"], negative)
            if scale is None:
                continue
            item = {
                "table": index,
                "row": row,
                "label": label,
                "cell": cell,
                "header": header.strip(),
            }
            item["scale"] = str(scale)
            period = parse_period(header, context)
            if single and not any(period.values()):
                # a one-column table whose header names no period takes a complete duration
                # from its caption or heading ('Three Months Ended June 30, 2025 (in millions)')
                whole = parse_period(context)
                if whole["end"] and (whole["months"] or whole["ytd"]):
                    period = whole
            item["period"] = {k: str(v) for k, v in period.items()}
            if excluded_header(header) or excluded_header(units[1]):
                continue  # a non-GAAP or partial column ('Non-GAAP Three Months Ended ...')
            if (
                currency == "other"
                or OTHER_CURRENCY_WORDS.search(header)
                or OTHER_CURRENCY_WORDS.search(wide_currency)  # header cells over every value
                or CONTEXT_CURRENCY.search(table_wide)
                or DECLARED_CURRENCY.search(table_wide)
            ):
                note("currency_mismatch", item)
                continue
            if not period_ok(period, spec):
                note(_period_result(period, spec), item)
            elif len(options) > 1 and scale != 1:
                note("scale_unverified", item)  # no unit phrase: the multiplier is inferred
            else:
                note("stated", item)
    prose = list(doc["blocks"])
    for table in doc["tables"]:  # prose laid out in a row is read as one text, cell by cell
        for cells in table["rows"]:
            texts = [c["text"] for c in cells if c["text"]]
            if texts and (not is_data_row(texts) or CONTINUES.search(texts[0])):
                prose.append(" ".join(texts))  # '... June 30, 2025 | was $5.2 million'
    for sentence in sentences(prose):
        current = None  # the label window that later unlabelled clauses refer to
        for clause in CLAUSE.split(sentence):
            labels = []  # (start, end, usable window or None when excluded)
            starts = [a[5] for a in money_amounts(clause)]
            for f in LABELS[concept].finditer(clause):
                upto = min([a for a in starts if a >= f.end()] or [len(clause)])
                before = clause[max(0, f.start() - 30) : f.start()]
                cut = list(PREFIX_BREAK.finditer(before))  # 'Adjusted EBITDA rose and net income'
                before = before[cut[-1].end() :] if cut else before
                excluded = EXCLUDED_LABEL.search(before + clause[f.start() : upto])
                window = None if excluded else clause[f.start() : f.end() + 10]
                labels.append((f.start(), f.end(), window))
            if any(window for _, _, window in labels):
                label_seen = True
            amounts = money_amounts(clause)
            for text, number, decimals, word, usd, at in amounts:
                before = [(end_, window) for start_, end_, window in labels if start_ < at]
                owner, since = before[-1][::-1] if before else (current, 0)
                between = clause[since:at]
                earlier = [a for a in amounts if since <= a[5] and a[5] + len(a[0]) <= at]
                # the text since the owner's last amount (or the label) introduces this amount
                gap = clause[earlier[-1][5] + len(earlier[-1][0]) : at] if earlier else between
                if not before and not earlier:
                    gap = ", " + gap  # an owner carried from an earlier clause: a new subject
                # the words after the amount up to the next amount or conjunction, at most 80
                after = at + len(text)
                stop = TRAIL_END.search(clause, after)
                ends = [a[5] for a in amounts if a[5] > at] + [len(clause), after + 80]
                trail = clause[after : min(ends + ([stop.start()] if stop else []))]
                if (
                    owner is None
                    or OTHER_METRIC.search(between)
                    or any(LABELS[other].search(between) for other in LABELS if other != concept)
                    or new_subject(gap)
                    or QUALIFIER.search(trail)  # '$5.2 million attributable to noncontrolling'
                    or FORWARD.search(clause)  # 'is expected to be', 'Our guidance: net income'
                ):
                    continue  # no label, an excluded measure, or another measure in between
                scale_options = scales(word) if word else [Decimal(1)]
                scale = equal(number, decimals, scale_options, spec["value"], negative_label(owner))
                if scale is None:
                    continue
                item = {
                    "sentence": sentence[:400],
                    "clause": clause[:400],
                    "label": owner,
                    "money": text,
                    "scale": str(scale),
                    "period": {k: str(v) for k, v in parse_period(clause).items()},
                    "fiscal_quarters": fiscal_quarters(clause),
                }
                if not usd:
                    note("currency_mismatch", item)
                    continue
                result = clause_result(clause, spec, len(amounts))
                note(result, item)  # different_period is kept as evidence but never ranked
            if labels:
                current = labels[-1][2]
    if best in ("stated", "period_unverified", "scale_unverified"):
        return best, evidence
    for image in doc["images"]:  # an image of the statement may still hold the USD value
        name = re.sub(r"[_\-+.]+", " ", unquote(image["src"]))  # 'income_statement.png'
        if STATEMENT_IMAGE[concept].search(" ".join([image["alt"], name, image["context"]])):
            return "exhibit_unavailable", evidence + [{"image": image, "reason": "image_dependent"}]
    if best:
        return best, evidence
    return ("label_only" if label_seen else "not_found"), evidence


def _period_result(period, spec):
    """An equal value counts as a different period, and is dropped, only when its parsed end date
    or duration contradicts the requirement; anything else unparsed is period_unverified."""
    if period["end"] is not None and abs((period["end"] - spec["end"]).days) > 7:
        return "different_period"
    months = period_months(period, spec)
    if spec["kind"] == "duration" and months is not None and months != spec["months"]:
        return "different_period"
    return "period_unverified"


# ------------------------------------------------------------- per-event analysis


def identify_release(documents):
    """documents: [{'description','type','url','kind','parsed'}] for fetched EX-99 documents."""
    candidates = [
        d
        for d in documents
        if RELEASE.search(d["description"])
        or (d.get("parsed") and RELEASE.search(d["parsed"]["text"][:3000]))
    ]
    if len(candidates) == 1:
        return "release", candidates
    if len(candidates) > 1:
        return "release_ambiguous", candidates
    ex991 = [d for d in documents if d["type"].upper() == "EX-99.1"]
    if len(ex991) == 1:
        return "release_by_type", ex991
    return "release_unidentified", []


def classify_component(release_docs, spec, concept):
    if spec is None:
        return "not_comparable", []
    best, evidence, seen = None, [], set()
    order = [  # possibly stated outcomes first: any candidate that may hold the value counts
        "stated",
        "period_unverified",
        "scale_unverified",
        "exhibit_unavailable",
        "currency_mismatch",
        "label_only",
        "not_found",
    ]
    for doc in release_docs:
        if doc["kind"] == "unsupported":
            reason = "fetch_failed" if doc.get("fetch_error") else "unsupported_format"
            result, items = "exhibit_unavailable", [{"reason": reason}]
        else:
            result, items = match_component(doc["parsed"], spec, concept)
        evidence += [dict(i, document=doc["url"], sha256=doc.get("sha256")) for i in items]
        seen.add(result)
    for result in order:
        if result in seen:
            best = result
            break
    return best or "not_found", evidence


def analyse_event(event, fetched, specs, frozen, calendar):
    """fetched: {'error', 'header', 'documents', 'overflow'} from saved bytes."""
    out = {
        "accession": event["accession"],
        "symbol": event["symbol"],
        "cik": event["cik"],
        "filing_date": event["filing_date"],
        "era": era(event["filing_date"]),
        "q_entry_session": event["q_entry_session"],
        "candidate": event["candidates"][0]["accession"],
        "event_status": None,
        "release": None,
        "components": {},
        "any_ex99": {},
    }
    status = None
    if fetched.get("error"):
        status = "exhibit_unavailable"
        out["reason"] = fetched["error"]
    else:
        header = fetched["header"]
        out["header"] = header
        if header["issues"]:
            status = "identity_failed"
        else:
            session = None
            if header["acceptance"] and header["filing_date"]:
                session = frozen.session(header["acceptance"], header["filing_date"], calendar)
            out["header_entry_session"] = session
            out["identity_unverified"] = bool(header["missing"]) or session is None
            if session is not None and session >= event["q_entry_session"]:
                status = "header_not_prior"
        if status is None and fetched.get("overflow"):
            status = "exhibit_unavailable"
            out["reason"] = "exhibit_overflow"
    release_docs = []
    if status is None:
        kind, release_docs = identify_release(fetched["documents"])
        out["release"] = {"kind": kind, "documents": [d["url"] for d in release_docs]}
        if kind == "release_unidentified":
            status = "exhibit_unavailable"
            out["reason"] = "release_unidentified"
    out["event_status"] = status or "examined"
    for name in COMPONENTS:
        spec = specs.get(name)
        if spec is None:
            out["components"][name] = {"classification": "not_comparable", "evidence": []}
        elif status is not None:
            out["components"][name] = {"classification": status, "evidence": []}
        else:
            result, evidence = classify_component(release_docs, spec, CONCEPT[name])
            out["components"][name] = {"classification": result, "evidence": evidence}
    readout = status is None or out.get("reason") == "release_unidentified"
    if readout and not out.get("identity_unverified"):  # only for a verified filer identity
        for name in COMPONENTS:
            if specs.get(name) is not None:
                result, _ = classify_component(fetched["documents"], specs[name], CONCEPT[name])
                out["any_ex99"][name] = result
    out["signals"] = {
        "S_flow": signal(out, S_FLOW),
        "Q_flow": signal(out, Q_FLOW),
        "assets": signal(out, ASSETS),
    }
    return out


def signal(event, names):
    classes = [event["components"][n]["classification"] for n in names]
    if "not_comparable" in classes:
        return {"comparable": False, "lower": False, "upper": False}
    flagged = (event.get("release") or {}).get("kind") == "release_ambiguous" or event.get(
        "identity_unverified", False
    )
    lower = all(c == "stated" for c in classes) and not flagged
    upper = all(c == "stated" or c in UNVERIFIED for c in classes)
    return {"comparable": True, "lower": lower, "upper": upper}


# ------------------------------------------------------------- statistics


def wilson(successes, n, z=1.959963984540054):
    if n == 0:
        return None, None
    p = successes / n
    centre = (p + z * z / (2 * n)) / (1 + z * z / n)
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return max(0.0, centre - half), min(1.0, centre + half)


def verdict(lower, upper, n, rules):
    lo_interval = wilson(lower, n)
    up_interval = wilson(upper, n)
    if n == 0:
        return "inconclusive", lo_interval, up_interval
    if lo_interval[0] >= rules["common_if_wilson_lower_at_least"]:
        return "release_complete_common", lo_interval, up_interval
    if up_interval[1] < rules["rare_if_wilson_upper_below"]:
        return "release_complete_rare", lo_interval, up_interval
    return "inconclusive", lo_interval, up_interval


def summarise(events, rules):
    def block(rows):
        out = {"events": len(rows), "signals": {}, "components": {}}
        for name in ("S_flow", "Q_flow", "assets"):
            comparable = [r for r in rows if r["signals"][name]["comparable"]]
            n = len(comparable)
            lower = sum(r["signals"][name]["lower"] for r in comparable)
            upper = sum(r["signals"][name]["upper"] for r in comparable)
            result, lo, up = verdict(lower, upper, n, rules)
            out["signals"][name] = {
                "comparable": n,
                "not_comparable": len(rows) - n,
                "lower_count": lower,
                "upper_count": upper,
                "lower_share": lower / n if n else None,
                "upper_share": upper / n if n else None,
                "wilson_lower_bound_interval": lo,
                "wilson_upper_bound_interval": up,
                "verdict": result if name != "assets" else None,
            }
        for name in COMPONENTS:
            counts = {}
            for r in rows:
                c = r["components"][name]["classification"]
                counts[c] = counts.get(c, 0) + 1
            single = [x for x in (signal(r, [name]) for r in rows) if x["comparable"]]
            n = len(single)
            lower = sum(x["lower"] for x in single)
            upper = sum(x["upper"] for x in single)
            _, lo, up = verdict(lower, upper, n, rules)
            out["components"][name] = {
                "classifications": dict(sorted(counts.items())),
                "comparable": n,
                "lower_count": lower,
                "upper_count": upper,
                "lower_share": lower / n if n else None,
                "upper_share": upper / n if n else None,
                "wilson_lower_bound_interval": lo,
                "wilson_upper_bound_interval": up,
            }
        statuses = {}
        for r in rows:
            statuses[r["event_status"]] = statuses.get(r["event_status"], 0) + 1
        out["event_status"] = dict(sorted(statuses.items()))
        kinds = [(r.get("release") or {}).get("kind") for r in rows]
        out["flags"] = {
            "identity_unverified": sum(bool(r.get("identity_unverified")) for r in rows),
            "release_ambiguous": kinds.count("release_ambiguous"),
            "release_by_type": kinds.count("release_by_type"),
        }
        any_counts = {}
        for name in COMPONENTS:
            any_counts[name] = sum(r["any_ex99"].get(name) == "stated" for r in rows)
        out["stated_in_any_ex99"] = any_counts
        return out

    return {
        "all": block(events),
        "by_era": {
            e: block([r for r in events if r["era"] == e]) for e in ("2012-2020", "2021-2025")
        },
    }


# ------------------------------------------------------------- processes, locks and fetching

WORKER = re.compile(r"python.*\.qualification[\\/]", re.I)


def processes():
    """(pid, parent pid, command line) for every running process; ProbeError if unavailable."""
    try:
        if os.name == "nt":
            query = (
                "Get-CimInstance Win32_Process | Select-Object ProcessId,ParentProcessId,"
                "CommandLine | ConvertTo-Json -Compress"
            )
            out = subprocess.run(
                ["powershell", "-NoProfile", "-NonInteractive", "-Command", query],
                capture_output=True,
                text=True,
                timeout=120,
                check=True,
            ).stdout
            rows = json.loads(out or "[]")
            rows = [rows] if isinstance(rows, dict) else rows
            return [
                (int(r["ProcessId"]), int(r["ParentProcessId"] or 0), r.get("CommandLine") or "")
                for r in rows
            ]
        out = subprocess.run(
            ["ps", "-axo", "pid=,ppid=,args="],
            capture_output=True,
            text=True,
            timeout=120,
            check=True,
        ).stdout
        rows = []
        for line in out.splitlines():
            parts = line.split(None, 2)
            if len(parts) >= 2:
                rows.append((int(parts[0]), int(parts[1]), parts[2] if len(parts) > 2 else ""))
        return rows
    except (OSError, subprocess.SubprocessError, ValueError, KeyError, TypeError) as exc:
        raise ProbeError("Running processes could not be listed: " + str(exc)) from exc


def other_workers():
    """Python processes running anything under .qualification, other than this process and its
    ancestors. Older SEC capture workers hold only their own lock, so the shared lock alone
    cannot show them."""
    rows = processes()
    parents = {pid: ppid for pid, ppid, _ in rows}
    mine, pid = set(), os.getpid()
    while pid and pid not in mine:
        mine.add(pid)
        pid = parents.get(pid)
    return [
        {"pid": pid, "command": command[:300]}
        for pid, _, command in rows
        if pid not in mine and WORKER.search(command)
    ]


@contextmanager
def exclusive(path, label):
    if not Path(path).is_file():
        raise ProbeError(label + " is missing: " + Path(path).as_posix())
    connection = sqlite3.connect(Path(path), timeout=0, isolation_level=None)
    try:
        try:
            connection.execute("BEGIN EXCLUSIVE")
        except sqlite3.OperationalError as exc:
            raise ProbeError(label + " is held by another process") from exc
        yield
    finally:
        try:
            connection.rollback()
        except sqlite3.Error:
            pass
        connection.close()


def study_lock(root):
    path = root / "probe.lock.sqlite"
    if not path.exists():
        sqlite3.connect(path).close()
    return path


def request_settings(definition):
    keys = [
        "max_lifetime_network_attempts",
        "max_attempts_per_url",
        "max_total_raw_bytes",
        "minimum_request_interval_seconds",
        "max_response_bytes",
        "timeout_seconds",
        "stop_http_status",
        "user_agent",
    ]
    return dict({k: definition["requests"][k] for k in keys}, reuse=[])


def wait_after_last_request(cache):
    """The frozen cache paces requests only within one process; before the first request of a
    resume, wait until the declared interval has passed since the last journaled request."""
    if not cache.starts:
        return
    last = datetime.fromisoformat(cache.starts[-1]["at"])
    elapsed = (datetime.now(timezone.utc) - last).total_seconds()
    interval = cache.request["minimum_request_interval_seconds"]
    if 0 <= elapsed < interval:
        time.sleep(interval - elapsed)


def acknowledged_stops(source):
    """STOP records the owner acknowledged (renamed beside the source)."""
    out = []
    for path in source.glob("STOP-acknowledged-*.json"):
        try:
            out.append(load(path))
        except (OSError, ValueError):
            continue
    return out


def acknowledged_urls(source):
    return {stop.get("url") for stop in acknowledged_stops(source)}


def quarantine_partial_raw(source):
    """Move aside raw files whose bytes no longer match their SHA256 name (a crash during the
    frozen cache's direct write), before the cache counts or reuses them; returns their names."""
    moved = []
    for path in sorted((source / "raw").glob("*.bin")):
        if sha(path.read_bytes()) != path.stem:
            target = source / "partial" / (path.name + "." + uuid.uuid4().hex)
            target.parent.mkdir(exist_ok=True)
            path.rename(target)
            moved.append(path.name)
    return moved


def source_manifest(source):
    """SHA256 of every saved source file: request journal, resource records, stops,
    quarantined parts and every raw payload, including one a crash left without its record."""
    return {
        path.relative_to(source).as_posix(): file_sha(path)
        for path in sorted(source.rglob("*"))
        if path.is_file()
    }


def quarantine_journal_tail(source, keep):
    """Move aside an incomplete last line of requests.jsonl (a crash during the frozen cache's
    append) before the cache parses the journal. The cache sends a request only after its
    request_started line is written, so a cut line is never a sent request. keep(record) saves
    the record before the journal is cut, so a crash in between loses nothing. A complete line
    that does not parse is not a crash tail and stops the run."""
    journal = source / "requests.jsonl"
    if not journal.exists():
        return None
    data = journal.read_bytes()
    complete, newline, tail = data.rpartition(b"\n")
    for line in complete.splitlines():
        try:
            json.loads(line)
        except ValueError as exc:
            raise ProbeError("requests.jsonl has an unreadable complete line; review it") from exc
    if not tail:
        return None
    target = source / "partial" / ("requests.jsonl.tail." + uuid.uuid4().hex)
    target.parent.mkdir(exist_ok=True)
    with open(target, "xb") as handle:
        handle.write(tail)
        handle.flush()
        os.fsync(handle.fileno())
    keep({"at": now(), "file": target.name, "bytes": len(tail), "sha256": sha(tail)})
    with open(journal, "r+b") as handle:
        handle.truncate(len(complete) + len(newline))
        handle.flush()
        os.fsync(handle.fileno())


def journal_mark(source):
    """Size and SHA256 of the request journal's complete lines."""
    journal = source / "requests.jsonl"
    data = journal.read_bytes() if journal.exists() else b""
    data = data[: data.rfind(b"\n") + 1]
    return {"bytes": len(data), "sha256": sha(data)}


def journal_problem(source, mark):
    """The journal must still begin with the complete lines recorded at the last checkpoint."""
    if not mark:
        return None
    journal = source / "requests.jsonl"
    data = journal.read_bytes() if journal.exists() else b""
    if len(data) < mark["bytes"] or sha(data[: mark["bytes"]]) != mark["sha256"]:
        return "Request journal differs from its recorded checkpoint; review it"
    return None


def fetch_event(frozen, cache, event, checkpoint=lambda: None):
    """Fetch index, header and EX-99 documents; return references to saved bytes.
    checkpoint() runs after every request outcome, so the journal so far is recorded."""
    capture = frozen.capture
    accession = event["candidates"][0]["accession"]
    base = capture.archive_base({"cik": event["cik"]}, accession)

    def get(url):
        try:
            return fetch(url)
        finally:
            checkpoint()

    def fetch(url):
        record = cache.root / "resources" / (capture.sha(url.encode()) + ".json")
        try:
            data, meta = cache.get(url)
            return data, None
        except capture.Halt:
            starts = sum(r["url"] == url for r in cache.starts)
            settings = cache.request
            if starts >= settings["max_attempts_per_url"]:
                status = "interrupted"
            elif len(cache.starts) >= settings["max_lifetime_network_attempts"]:
                status = "lifetime_ceiling"
            elif cache.used_bytes >= settings["max_total_raw_bytes"]:
                status = "byte_ceiling"
            else:
                raise
            if record.exists():
                raise
            # A ceiling reached before an outcome: stop once for the owner's review, then record
            # a terminal failure (never requested again). STOP.json is written first, so a crash
            # between the two still needs the review. A per-URL stop covers its own URL; an
            # acknowledged lifetime or byte stop covers every later URL.
            failure = {
                "url": url,
                "status": status,
                "error": "Attempt ceiling reached (" + status + ") before an outcome",
            }
            reviewed = any(
                a.get("status") == status and (a.get("url") == url or status != "interrupted")
                for a in acknowledged_stops(cache.root)
            )
            if not reviewed:
                (cache.root / "STOP.json").write_text(
                    json.dumps(dict(failure, at=now())), encoding="utf-8"
                )
            write_json(frozen, record, failure)
            if not reviewed:
                raise capture.Halt("Attempt ceiling reached; review, then resume")
            return None, failure["error"]
        except capture.CaptureError as exc:
            # A transport failure (no HTTP status) stops the attempt until the owner acknowledges
            # it, even if a crash came between saving the failure and writing STOP.json.
            if record.exists() and load(record).get("status") is None:
                if url not in acknowledged_urls(cache.root):
                    (cache.root / "STOP.json").write_text(
                        json.dumps({"url": url, "error": str(exc), "at": now()}), encoding="utf-8"
                    )
                    raise capture.Halt("Transport failure; check the network, then resume") from exc
            return None, str(exc)

    index, error = get(base + accession + "-index.html")
    if error:
        return {"error": "index: " + error}
    try:
        documents = parse_8k_index(capture, index, base, accession)
    except capture.CaptureError as exc:
        return {"error": "index: " + str(exc)}
    header, error = get(base + accession + ".hdr.sgml")
    if error:
        return {"error": "header: " + error}
    if len(documents) > 10:
        return {"documents": documents, "overflow": True}
    for doc in documents:
        data, error = get(doc["url"])
        doc["error"] = error
    return {"documents": documents}


def saved(cache_root, capture, url):
    record = cache_root / "resources" / (capture.sha(url.encode()) + ".json")
    if not record.exists():
        return None, "not fetched"
    meta = load(record)
    data = None
    if "path" in meta:  # any saved payload, an error response's included, must be unchanged
        try:
            data = (cache_root / meta["path"]).read_bytes()
        except OSError as exc:
            raise ProbeError("Saved response missing: " + url) from exc
        if len(data) != meta.get("bytes") or sha(data) != meta.get("sha256"):
            raise ProbeError("Saved response changed: " + url)
    if meta.get("error") or meta.get("status") != 200:
        return None, meta.get("error") or "HTTP " + str(meta.get("status"))
    return data, None


def rebuild_fetched(frozen, cache_root, event):
    """Reconstruct an event's fetched material only from saved bytes."""
    capture = frozen.capture
    accession = event["candidates"][0]["accession"]
    base = capture.archive_base({"cik": event["cik"]}, accession)
    index, error = saved(cache_root, capture, base + accession + "-index.html")
    if error:
        return {"error": "index: " + error}
    try:
        documents = parse_8k_index(capture, index, base, accession)
    except capture.CaptureError as exc:
        return {"error": "index: " + str(exc)}
    raw_header, error = saved(cache_root, capture, base + accession + ".hdr.sgml")
    if error:
        return {"error": "header: " + error}
    header = header_identity(decode(raw_header), event["cik"], accession)
    if len(documents) > 10:
        return {"header": header, "documents": [], "overflow": True}
    out = []
    for doc in documents:
        data, error = saved(cache_root, capture, doc["url"])
        if error:
            entry = dict(doc, kind="unsupported", parsed=None, fetch_error=error)
        else:
            kind = document_kind(doc["url"], data)
            parsed = parse_document(kind, data) if kind != "unsupported" else None
            entry = dict(doc, kind=kind, parsed=parsed, sha256=sha(data))
        out.append(entry)
    return {"header": header, "documents": out}


# ------------------------------------------------------------- attempt lifecycle


def write_json(frozen, path, value):
    return frozen.audit.write_json(Path(path), value)


def attempts(root):
    folder = root / "attempts"
    if not folder.exists():
        return []
    out = []
    for path in sorted(folder.iterdir()):
        if path.name.startswith("."):
            continue  # an uninitialised staging folder (see run); preflight lists it
        try:
            out.append((path, load(path / "attempt.json")))
        except (OSError, ValueError):
            out.append((path, {"status": "unreadable"}))
    return out


def prepare(definition, repo, frozen):
    """Everything a run needs before its first request; raises ProbeError on any problem."""
    problems = input_problems(repo, definition)
    if problems:
        raise ProbeError("Inputs missing or changed: " + json.dumps(problems))
    identity, runtime = runtime_problems(frozen, definition)
    if runtime:
        raise ProbeError("; ".join(runtime))
    paths = definition["paths"]
    events = load(repo / paths["timing_events"])
    events = events["events"] if isinstance(events, dict) else events
    sample = draw_sample(events, definition["sample"]["size"])
    if len(frame(events)) != definition["population"]["size"]:
        raise ProbeError("Frame size differs from the declaration")
    calendar = load(repo / paths["calendar"])
    calendar = calendar["sessions"] if isinstance(calendar, dict) else calendar
    for event in sample:
        if (
            frozen.session(event["acceptance"], event["filing_date"], calendar)
            != event["q_entry_session"]
        ):
            raise ProbeError("10-Q session not reproduced: " + event["accession"])
    return identity, sample, calendar


def run(
    definition_path=DEFINITION,
    freeze_path=FREEZE,
    repo=REPO,
    root=ROOT,
    opener=None,
    resume=None,
    acknowledge_stop=False,
):
    definition, definition_sha, problems = declaration_problems(definition_path, freeze_path, repo)
    if problems:
        raise ProbeError(problems[0])
    frozen = Frozen(repo)
    with (
        exclusive(study_lock(root), "Study lock"),
        exclusive(repo / definition["paths"]["shared_source_lock"], "Shared SEC source lock"),
    ):
        workers = other_workers()
        if workers:
            raise ProbeError("Other research workers are running: " + json.dumps(workers))
        previous = attempts(root)  # checked under the study lock
        if resume is None and previous:
            raise ProbeError(
                "An attempt already exists for this study; resume it or declare an amendment"
            )
        if resume is not None:
            match = [a for p, a in previous if p.name == resume]
            if not match:
                raise ProbeError("No such attempt: " + resume)
            if match[0].get("status") not in ("running", "halted"):
                raise ProbeError(
                    "Attempt is "
                    + str(match[0].get("status"))
                    + "; only running or halted attempts resume"
                )
        identity, sample, calendar = prepare(definition, repo, frozen)
        attempt = root / "attempts" / (resume or uuid.uuid4().hex)
        record = attempt / "attempt.json"
        if resume:
            meta = load(record)
        else:
            meta = {
                "attempt": attempt.name,
                "study": STUDY,
                "definition_sha256": definition_sha,
                "code": load(freeze_path)["code"],
                "inputs": definition["inputs"],
                "started_at_utc": now(),
                "resumes": [],
                "status": "running",
                "runtime": identity,
            }
            # The directory becomes visible only with its record: a crash before the rename
            # leaves a dot-named staging folder that made no request and is not an attempt.
            staging = attempt.parent / ("." + attempt.name + ".init")
            staging.mkdir(parents=True)
            write_json(frozen, staging / "attempt.json", meta)
            staging.rename(attempt)
        if resume:
            if meta["definition_sha256"] != definition_sha:
                raise ProbeError("Attempt belongs to another definition")
            if meta.get("code") != load(freeze_path)["code"]:
                raise ProbeError("Attempt was started under other code; it cannot be resumed")
            stop = attempt / "source" / "STOP.json"
            if stop.exists():
                if not acknowledge_stop:
                    raise ProbeError(
                        "STOP.json present; review it, then resume with --acknowledge-stop"
                    )
                stop.rename(
                    attempt / "source" / ("STOP-acknowledged-" + uuid.uuid4().hex + ".json")
                )
            meta["resumes"].append({"at": now(), "runtime": identity})
        meta.update(status="running")  # meta["runtime"] stays the identity the attempt began with
        write_json(frozen, record, meta)
        accessions = [e["accession"] for e in sample]
        if (attempt / "sample.json").exists():
            if load(attempt / "sample.json") != accessions:
                raise ProbeError("Saved sample differs from the recomputed sample")
        else:
            write_json(frozen, attempt / "sample.json", accessions)
        projection = attempt / "projection.json"
        if not projection.exists():
            values = project_values(frozen, repo / definition["paths"]["records"], accessions)
            meta["projection_sha256"] = write_json(frozen, projection, values)
            write_json(frozen, record, meta)
        elif meta.get("projection_sha256") is None:
            # Written atomically by this attempt before a crash; bind it before any request.
            values = project_values(frozen, repo / definition["paths"]["records"], accessions)
            if load(projection) != json.loads(json.dumps(values)):
                raise ProbeError("Saved projection does not match records.json for this sample")
            meta["projection_sha256"] = file_sha(projection)
            write_json(frozen, record, meta)
        elif file_sha(projection) != meta["projection_sha256"]:
            raise ProbeError("Saved projection differs from the one the attempt recorded")
        (attempt / "source").mkdir(exist_ok=True)
        if (attempt / "source" / "raw").is_dir():
            moved = quarantine_partial_raw(attempt / "source")
            if moved:
                meta.setdefault("quarantined_partial_raw", []).append({"at": now(), "files": moved})
                write_json(frozen, record, meta)

        def keep(tail):
            meta.setdefault("quarantined_journal_tail", []).append(tail)
            write_json(frozen, record, meta)

        quarantine_journal_tail(attempt / "source", keep)
        problem = journal_problem(attempt / "source", meta.get("journal"))
        if problem:
            raise ProbeError(problem)  # an edited journal would reset the request counters

        def checkpoint():
            meta["journal"] = journal_mark(attempt / "source")
            write_json(frozen, record, meta)

        cache = frozen.capture.Cache(attempt / "source", request_settings(definition), repo, opener)
        wait_after_last_request(cache)
        try:
            for event in sample:
                fetch_event(frozen, cache, event, checkpoint)
        except frozen.capture.Halt as exc:
            meta.update(status="halted", halted_at_utc=now(), halt=str(exc))
            write_json(frozen, record, meta)
            raise ProbeError("Halted: " + str(exc)) from exc
        except Exception as exc:
            meta.update(status="failed", failed_at_utc=now(), error=repr(exc))
            write_json(frozen, record, meta)
            raise
        try:
            outputs = analyse(frozen, definition, repo, attempt, sample, calendar)
        except Exception as exc:
            meta.update(status="failed", failed_at_utc=now(), error=repr(exc))
            write_json(frozen, record, meta)
            raise
        manifest = source_manifest(attempt / "source")
        meta.update(status="complete", finished_at_utc=now(), files=outputs, source=manifest)
        write_json(frozen, record, meta)
        return attempt


def analyse(frozen, definition, repo, attempt, sample, calendar):
    values = load(attempt / "projection.json")
    rows = []
    for event in sample:
        fetched = rebuild_fetched(frozen, attempt / "source", event)
        specs = comparison(values.get(event["accession"]))
        rows.append(analyse_event(event, fetched, specs, frozen, calendar))
    files = {}
    for name, value in outputs(rows, definition).items():
        files[name] = write_json(frozen, attempt / name, value)
    return files


def outputs(rows, definition):
    """The attempt's output files as the JSON values they hold."""
    summary = summarise(rows, definition["interpretation"]["thresholds"])
    spot = sorted(rows, key=lambda r: sha((STUDY + "|spot|" + r["accession"]).encode()))[:20]
    out = {}
    for name, value in (
        ("events.json", rows),
        ("summary.json", summary),
        (
            "spot-check.json",
            [
                {
                    k: r.get(k)
                    for k in (
                        "accession",
                        "symbol",
                        "candidate",
                        "event_status",
                        "identity_unverified",
                        "release",
                        "components",
                    )
                }
                for r in spot
            ],
        ),
    ):
        out[name] = json.loads(json.dumps(value, default=str))
    return out


def same_runtime(identity, began):
    """Same Python minor version, implementation and America/New_York zone data."""
    keys = ("implementation", "tzdata_package", "new_york_tzif_sha256")
    minor = [str(r.get("python", "")).rsplit(".", 1)[0] for r in (identity, began)]
    return minor[0] == minor[1] and all(identity.get(k) == began.get(k) for k in keys)


def reanalyze(attempt_id, definition_path=DEFINITION, freeze_path=FREEZE, repo=REPO, root=ROOT):
    """Recompute every output from saved bytes in memory and compare; writes nothing."""
    definition, definition_sha, problems = declaration_problems(definition_path, freeze_path, repo)
    if problems:
        raise ProbeError(problems[0])
    frozen = Frozen(repo)
    identity, runtime = runtime_problems(frozen, definition)
    if runtime:
        raise ProbeError("; ".join(runtime))
    attempt = root / "attempts" / attempt_id
    meta = load(attempt / "attempt.json")
    if meta.get("definition_sha256") != definition_sha or meta.get("status") != "complete":
        raise ProbeError("Only a complete attempt of this definition can be reanalysed")
    if meta.get("code") != load(freeze_path)["code"]:
        raise ProbeError("Attempt was produced by other code; it cannot be reanalysed")
    if meta.get("inputs") != definition["inputs"]:
        raise ProbeError("Attempt was produced from other inputs")
    paths = definition["paths"]
    for relative in [r for r in definition["inputs"] if r != paths["records"]]:
        # records.json is not read; the recorded projection SHA256 is checked instead
        if (
            not (repo / relative).is_file()
            or file_sha(repo / relative) != definition["inputs"][relative]
        ):
            raise ProbeError("Input missing or changed: " + relative)
    if file_sha(attempt / "projection.json") != meta.get("projection_sha256"):
        raise ProbeError("Saved projection differs from the one the attempt recorded")
    events = load(repo / definition["paths"]["timing_events"])
    events = events["events"] if isinstance(events, dict) else events
    by_accession = {e["accession"]: e for e in events}
    sample = [by_accession[a] for a in load(attempt / "sample.json")]
    calendar = load(repo / definition["paths"]["calendar"])
    calendar = calendar["sessions"] if isinstance(calendar, dict) else calendar
    values = load(attempt / "projection.json")
    rows = [
        analyse_event(
            e,
            rebuild_fetched(frozen, attempt / "source", e),
            comparison(values.get(e["accession"])),
            frozen,
            calendar,
        )
        for e in sample
    ]
    expected = outputs(rows, definition)
    recorded = meta.get("files") or {}
    check = {
        "events_identical": expected["events.json"] == load(attempt / "events.json"),
        "summary_identical": expected["summary.json"] == load(attempt / "summary.json"),
        "spot_check_identical": expected["spot-check.json"] == load(attempt / "spot-check.json"),
        # the saved bytes are the ones the run wrote, not a rewrite with equal content
        "files_match_record": set(recorded) == set(expected)
        and all(file_sha(attempt / name) == recorded[name] for name in expected),
        # the journal, resource records and stops are the ones the run left
        "source_matches_record": source_manifest(attempt / "source") == meta.get("source"),
        # the interpreter and time-zone data the attempt began with
        "runtime_matches_record": same_runtime(identity, meta.get("runtime") or {}),
        "recorded_files": recorded,
    }
    check["reproduced"] = all(v for k, v in check.items() if k != "recorded_files")
    return check


def preflight(definition_path=DEFINITION, freeze_path=FREEZE, repo=REPO, root=ROOT):
    """What a run would meet, without any request or write."""
    definition, _, problems = declaration_problems(definition_path, freeze_path, repo)
    blocking = [{"path": "declaration", "problem": p} for p in problems]
    if problems:
        return {"ready": False, "blocking": blocking}
    blocking += input_problems(repo, definition)
    for path, label in (
        (root / "probe.lock.sqlite", "study lock"),
        (repo / definition["paths"]["shared_source_lock"], "shared SEC source lock"),
    ):
        busy = None
        if path.exists():
            frozen_audit = verified_module(AUDIT[0], AUDIT[1], "exhibit_probe_preflight", repo)
            busy = frozen_audit.lock_busy(path)
        elif label == "shared SEC source lock":
            busy = "missing"
        if busy:
            blocking.append({"path": label, "problem": busy})
    try:
        workers = other_workers()
    except ProbeError as exc:
        workers = [{"problem": str(exc)}]
    if workers:
        blocking.append({"path": "processes", "problem": workers})
    resumable = [p.name for p, a in attempts(root) if a.get("status") in ("running", "halted")]
    if attempts(root) and not resumable:
        blocking.append({"path": "attempts", "problem": "a completed or failed attempt exists"})
    staging = sorted(p.name for p in (root / "attempts").glob(".*"))  # empty if absent
    result = {
        "ready": not blocking,
        "blocking": blocking,
        "resumable_attempts": resumable,
        "uninitialised_staging": staging,
    }
    if blocking:
        return result
    frozen = Frozen(repo)
    try:
        identity, sample, _ = prepare(definition, repo, frozen)
    except ProbeError as exc:
        return {"ready": False, "blocking": [{"path": "prepare", "problem": str(exc)}]}
    result.update(sample_size=len(sample), runtime=identity)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--preflight", action="store_true")
    group.add_argument("--run", action="store_true")
    group.add_argument("--resume")
    group.add_argument("--reanalyze")
    parser.add_argument("--acknowledge-stop", action="store_true")
    args = parser.parse_args()
    if args.preflight:
        print(json.dumps(preflight(), indent=1, default=str))
    elif args.reanalyze:
        check = reanalyze(args.reanalyze)
        print(json.dumps(check, indent=1))
        sys.exit(0 if check["reproduced"] else 1)
    else:
        print(
            json.dumps(
                {"attempt": str(run(resume=args.resume, acknowledge_stop=args.acknowledge_stop))}
            )
        )
