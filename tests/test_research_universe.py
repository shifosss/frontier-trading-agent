import io
import json
import zipfile
from xml.sax.saxutils import escape

import httpx
import pytest

from frontier.research_universe import (
    NASDAQ_URL,
    OTHER_URL,
    TMX_URL,
    build_membership,
    discover_universe,
    load_snapshot,
    parse_nasdaq_directory,
    parse_tmx_workbook,
)

NASDAQ = (
    "Symbol|Security Name|Market Category|Test Issue|Financial Status|"
    "Round Lot Size|ETF|NextShares\n"
    """AAPL|Apple Inc. - Common Stock|Q|N|N|100|N|N
BAD|Fixture - Common Stock|G|N|D|100|N|N
NEXT|Fixture NextShares|G|N|N|100|Y|Y
SPY|SPDR S&P 500 ETF Trust|G|N|N|100|Y|N
TEST|Fixture - Common Stock|G|Y|N|100|N|N
TQQQ|ProShares UltraPro QQQ|G|N|N|100|Y|N
WARR|Fixture - Warrants|G|N|N|100|N|N
File Creation Time: 0918202614:01|||||||
"""
)
OTHER = """ACT Symbol|Security Name|Exchange|CQS Symbol|ETF|Round Lot Size|Test Issue|NASDAQ Symbol
BRK.B|Berkshire Hathaway Inc. Class B Common Stock|N|BRK.B|N|100|N|BRK.B
ADR|Fixture American Depositary Shares|N|ADR|N|100|N|ADR
UNIT|Fixture Units each consisting of common shares and warrants|N|UNIT|N|100|N|UNIT
ZZ|Fixture Common Stock|X|ZZ|N|100|N|ZZ
File Creation Time: 0918202614:01||||||
"""
BASELINE = [
    {"symbol": "SPY", "asset_type": "etf", "group": "us-broad"},
    {"symbol": "XIU.TO", "asset_type": "etf", "group": "ca-broad"},
]


def tmx_fixture():
    headers = [
        "Exchange",
        "Name",
        "Root\nTicker",
        "Sector",
        "SP_Type",
        "Market Cap (C$)\n31-August-2026",
        "Value (C$) YTD\n31-August-2026",
    ]
    rows = [
        headers,
        ["TSX", "Fixture Company", "FIX.A", "Industrials", "", "100000", "50000"],
        [
            "TSX",
            "iShares S&P/TSX 60 Index ETF",
            "XIU",
            "ETP",
            "Exchange Traded Funds",
            "1000",
            "800",
        ],
        ["TSX", "Unreviewed ETF", "UP", "ETP", "Exchange Traded Funds", "1000", "800"],
        ["TSX", "Fixture CDR", "CDR", "CDR", "CDR", "1000", "800"],
        ["TSX", "Fixture REIT Trust", "TR", "Real Estate", "", "1000", "800"],
    ]
    strings = list(dict.fromkeys(str(value) for row in rows for value in row))
    ns = 'xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"'
    sheet = f"<worksheet {ns}><sheetData>"
    for index, row in enumerate(rows, 10):
        sheet += f'<row r="{index}">'
        for col, value in enumerate(row):
            sheet += f'<c r="{chr(65 + col)}{index}" t="s"><v>{strings.index(value)}</v></c>'
        sheet += "</row>"
    sheet += "</sheetData></worksheet>"
    content = io.BytesIO()
    with zipfile.ZipFile(content, "w") as book:
        book.writestr(
            "xl/sharedStrings.xml",
            f"<sst {ns}>"
            + "".join(f"<si><t>{escape(value)}</t></si>" for value in strings)
            + "</sst>",
        )
        book.writestr(
            "xl/workbook.xml",
            f"<workbook {ns} "
            'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
            '<sheets><sheet name="TSX Issuers August 2026" r:id="rId1"/>'
            '<sheet name="TSXV Issuers August 2026" r:id="rId2"/></sheets></workbook>',
        )
        book.writestr(
            "xl/_rels/workbook.xml.rels",
            "<Relationships>"
            '<Relationship Id="rId1" Target="worksheets/sheet1.xml"/>'
            '<Relationship Id="rId2" Target="worksheets/sheet2.xml"/></Relationships>',
        )
        book.writestr("xl/worksheets/sheet1.xml", sheet)
        book.writestr("xl/worksheets/sheet2.xml", sheet.replace("TSX", "TSXV"))
    return content.getvalue()


def test_official_flags_and_types_filter_without_symbol_length_heuristics():
    first, vintage = parse_nasdaq_directory(NASDAQ, "nasdaq")
    second, _ = parse_nasdaq_directory(OTHER.encode(), "other_us")
    records, excluded = build_membership(first + second, BASELINE)
    assert [item["symbol"] for item in records] == ["AAPL", "BRK-B", "SPY"]
    assert vintage == "0918202614:01"
    assert records[1]["source_symbol"] == "BRK.B"
    reasons = {item["symbol"]: item["reason"] for item in excluded}
    assert reasons["TEST"] == "test_issue"
    assert reasons["BAD"] == "non_normal_nasdaq_financial_status"
    assert reasons["NEXT"] == "nextshares"
    assert reasons["TQQQ"] == "etf_leverage_classification_not_verified"
    assert reasons["ZZ"] == "unknown_exchange_code"
    assert reasons["ADR"] == reasons["WARR"] == reasons["UNIT"] == "non_common_security"
    reversed_records, reversed_excluded = build_membership(list(reversed(first + second)), BASELINE)
    assert (records, excluded) == (reversed_records, reversed_excluded)


def test_tmx_keeps_month_and_root_identity_without_claiming_security_mapping():
    rows, vintage = parse_tmx_workbook(tmx_fixture())
    assert len(rows) == 5
    assert vintage == "August 2026"
    records, excluded = build_membership(rows, BASELINE)
    assert [item["symbol"] for item in records] == ["FIX-A.TO", "XIU.TO"]
    assert records[0]["symbol_identity"] == "issuer_root_requires_provider_verification"
    assert records[0]["market_cap_cad"] == 100000
    assert records[0]["ytd_value_cad"] == 50000
    assert records[1]["asset_type"] == "etf"
    assert len(excluded) == 3


def test_dated_discovery_is_replayable_and_does_not_change_active_universe(tmp_path):
    config = tmp_path / "config/scanner_universe.json"
    config.parent.mkdir()
    config.write_text(json.dumps(BASELINE), encoding="utf-8")
    original = config.read_bytes()
    documents = {NASDAQ_URL: NASDAQ.encode(), OTHER_URL: OTHER.encode(), TMX_URL: tmx_fixture()}
    client = httpx.Client(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(200, content=documents[str(request.url)])
        )
    )
    first = discover_universe(tmp_path, client=client, captured_at="2026-09-18T19:00:00+00:00")
    second = discover_universe(tmp_path, client=client, captured_at="2026-09-19T19:00:00+00:00")
    assert not client.is_closed
    assert first["membership_sha256"] == second["membership_sha256"]
    assert first["snapshot_id"] != second["snapshot_id"]
    assert first["historical_membership"] is False
    assert first["eligible_count"] == 5
    assert first["observed_count"] == 16
    assert first["counts"] == {"USD_stock": 2, "USD_etf": 1, "CAD_stock": 1, "CAD_etf": 1}
    assert config.read_bytes() == original
    assert load_snapshot(tmp_path) == second
    assert load_snapshot(tmp_path, first["snapshot_id"]) == first
    assert not (tmp_path / "data/scanner").exists()
    assert not (tmp_path / "data/operator.sqlite").exists()
    source = tmp_path / first["sources"][0]["path"]
    source.write_bytes(source.read_bytes() + b"changed")
    with pytest.raises(ValueError, match="source bytes changed"):
        load_snapshot(tmp_path)


def test_invalid_or_incomplete_source_is_not_saved_as_current_membership(tmp_path):
    with pytest.raises(ValueError, match="timestamp"):
        parse_nasdaq_directory(NASDAQ.split("File Creation Time:")[0], "nasdaq")
    with pytest.raises(ValueError, match="schema"):
        parse_nasdaq_directory("Symbol|Name\nA|Alpha\nFile Creation Time: now|", "nasdaq")
    with pytest.raises(ValueError, match="timezone"):
        discover_universe(tmp_path, captured_at="2026-09-18T19:00:00")
    with pytest.raises(ValueError, match="snapshot ID"):
        load_snapshot(tmp_path, "../../private")
    client = httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(503)))
    with pytest.raises(httpx.HTTPStatusError):
        discover_universe(tmp_path, client=client)
    assert not (tmp_path / "data/research/universe/latest.json").exists()
