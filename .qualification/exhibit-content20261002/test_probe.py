"""Offline synthetic checks for the exhibit-content probe. No SEC, price or outcome data."""

import hashlib
import http.client
import importlib.util
import io
import json
import os
import shutil
import socket
import sqlite3
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path
from urllib.error import HTTPError, URLError

import pytest

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]


def module():
    spec = importlib.util.spec_from_file_location("exhibit_probe_under_test", HERE / "probe.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


m = module()
DEFINITION = json.loads((HERE / "definition.json").read_text(encoding="utf-8"))


def sha(data):
    return hashlib.sha256(data).hexdigest()


# ------------------------------------------------------------------ fixtures


def group(*values):
    """Each value is a ($, number, closing) triple in its own three physical columns."""
    return "".join(f"<td>{a}</td><td>{b}</td><td>{c}</td>" for a, b, c in values)


def plain(*values):
    return group(*[("", v, "") for v in values])


def release_html(ni=("5.2", "(1.1"), ytd_ni=("8.0", "3.0"), cfo=("14.0", "6.0"), assets="1,400"):
    close = ")" if ni[1].startswith("(") else ""
    years = "".join(f'<td colspan="3">{y}</td>' for y in (2025, 2024, 2025, 2024))
    net = group(("$", ni[0], ""), ("$", ni[1], close), ("$", ytd_ni[0], ""), ("$", ytd_ni[1], ""))
    return f"""<html><body><p>ACME Reports Second Quarter Fiscal 2025 Results</p>
<p>Net income for the second quarter of fiscal 2025 was $5.2 million.</p>
<p>Condensed Consolidated Statements of Operations (in millions)</p>
<table>
<tr><td></td><td colspan="6">Three Months Ended June 30,</td>
<td colspan="6">Six Months Ended June 30,</td></tr>
<tr><td></td>{years}</tr>
<tr><td>Net income (loss)</td>{net}</tr>
<tr><td>Adjusted net income</td>{plain("9.9", "5.2", "12.0", "7.0")}</tr>
<tr><td>Net cash provided by operating activities</td>{plain("7.5", "2.0", *cfo)}</tr>
</table>
<p>Balance sheet (in millions)</p>
<table><tr><td></td><td colspan="3">June 30, 2025</td><td colspan="3">December 31, 2024</td></tr>
<tr><td>Total assets</td>{group(("$", "1,500", ""), ("$", assets, ""))}</tr></table>
</body></html>""".encode()


RECORD = {
    "accession": "0000000001-24-000010",
    "status": "qualified",
    "q_status": "qualified",
    "fiscal_year": 2025,
    "fiscal_period": "Q2",
    "prior_fy_end": "2024-12-31",
    "current_ni": "5200000",
    "prior_ni": "-1100000",
    "prior_fy_assets": "1400000000",
    "current_start": "2025-04-01",
    "current_end": "2025-06-30",
    "prior_start": "2024-04-01",
    "prior_end": "2024-06-30",
    "q_current_cfo": "14000000",
    "q_current_ni": "8000000",
    "q_prior_cfo": "6000000",
    "q_prior_ni": "3000000",
    "q_current_start": "2025-01-01",
    "q_current_end": "2025-06-30",
    "q_prior_start": "2024-01-01",
    "q_prior_end": "2024-06-30",
}


def classify(html, record=RECORD, kind="html"):
    doc = m.parse_document(kind, html)
    specs = m.comparison(record)
    return {name: m.match_component(doc, specs[name], m.CONCEPT[name])[0] for name in m.COMPONENTS}


# ------------------------------------------------------------------ matching rules


def test_full_release_states_every_component():
    assert set(classify(release_html()).values()) == {"stated"}


def test_split_header_rows_and_split_currency_cells():
    doc = m.parse_document("html", release_html())
    cells = list(m.table_cells(doc["tables"][0]))
    first = cells[0]
    assert first[1] == "$5.2" and first[2] == "Three Months Ended June 30, 2025"
    assert cells[1][1] == "$(1.1)"
    assert m.parse_number("$(1.1)") == (Decimal("-1.1"), 1, "USD")


def test_adjusted_row_never_states_a_gaap_value():
    # Only the adjusted row holds 5.2 for the current quarter; the GAAP row shows 4.0.
    html = release_html(ni=("4.0", "(1.1")).replace(b"was $5.2 million", b"was $4.0 million")
    assert classify(html)["current_ni"] == "label_only"


def test_value_under_a_different_period_does_not_count():
    # The quarterly value appears only under the six-month column.
    html = release_html(ni=("9.0", "(1.1"), ytd_ni=("5.2", "3.0"))
    html = html.replace(b"was $5.2 million", b"was strong")
    assert classify(html)["current_ni"] == "label_only"


def test_unreadable_header_is_period_unverified():
    html = b"""<table><tr><td></td><td>Current</td><td>Prior</td></tr>
    <tr><td>Net income</td><td>5.2</td><td>(1.1)</td></tr></table><p>(in millions)</p>"""
    assert classify(html)["current_ni"] == "period_unverified"


def table(header, *rows, before=b"<p>(in millions)</p>"):
    cells = b"".join(b"<tr><td>" + b"</td><td>".join(r) + b"</td></tr>" for r in rows)
    head = b"<tr><td></td><td>" + b"</td><td>".join(header) + b"</td></tr>"
    return before + b"<table>" + head + cells + b"</table>"


def test_stacked_sections_take_their_own_header():
    html = b"""<p>(in millions)</p><table>
<tr><td></td><td>Three Months Ended June 30,</td><td></td></tr>
<tr><td></td><td>2025</td><td>2024</td></tr>
<tr><td>Revenue</td><td>90.0</td><td>80.0</td></tr>
<tr><td>Gross margin</td><td>45%</td><td>44%</td></tr>
<tr><td>Net income</td><td>5.2</td><td>(1.1)</td></tr>
<tr><td>Operating activities:</td><td></td><td></td></tr>
<tr><td></td><td>Six Months Ended June 30,</td><td></td></tr>
<tr><td></td><td>2025</td><td>2024</td></tr>
<tr><td>Net income</td><td>8.0</td><td>3.0</td></tr>
<tr><td>Net cash provided by operating activities</td><td>14.0</td><td>6.0</td></tr>
</table>"""
    result = classify(html)
    assert {result[n] for n in m.S_FLOW + m.Q_FLOW} == {"stated"}


def test_loss_and_cash_used_labels_sign_unsigned_amounts():
    loss = dict(RECORD, current_ni="-3000000", q_current_cfo="-14000000")
    html = table([b"Three Months Ended June 30, 2025"], [b"Net loss", b"3.0"])
    assert classify(html, loss)["current_ni"] == "stated"
    mixed = table([b"Three Months Ended June 30, 2025"], [b"Net (loss) income", b"3.0"])
    assert classify(mixed, loss)["current_ni"] == "label_only"
    signed = table([b"Three Months Ended June 30, 2025"], [b"Net (loss) income", b"(3.0)"])
    assert classify(signed, loss)["current_ni"] == "stated"
    used = (
        b"<p>Net cash used in operating activities for the six months ended June 30, 2025"
        b" was $14.0 million.</p>"
    )
    assert classify(used, loss)["q_current_cfo"] == "stated"
    assert classify(used)["q_current_cfo"] == "label_only"


def test_narrative_amounts_pair_with_their_own_clause():
    record = dict(RECORD, prior_ni="1100000")
    right = (
        b"<p>Net income for the second quarter of 2025 was $5.2 million, compared with"
        b" $1.1 million in the second quarter of 2024.</p>"
    )
    swapped = right.replace(b"$5.2", b"$X").replace(b"$1.1", b"$5.2").replace(b"$X", b"$1.1")
    unpaired = (
        b"<p>Net income for the three months ended June 30, 2025 and June 30, 2024 was"
        b" $5.2 million and $1.1 million.</p>"
    )
    assert [classify(right, record)[n] for n in ("current_ni", "prior_ni")] == ["stated"] * 2
    assert [classify(swapped, record)[n] for n in ("current_ni", "prior_ni")] == ["label_only"] * 2
    assert classify(unpaired, record)["current_ni"] == "period_unverified"
    signs = dict(RECORD, current_ni="-3000000", prior_ni="1100000")
    mixed = (
        b"<p>Net loss for the second quarter of 2025 was $3.0 million, compared with net income"
        b" of $1.1 million in the second quarter of 2024.</p>"
    )
    assert [classify(mixed, signs)[n] for n in ("current_ni", "prior_ni")] == ["stated"] * 2
    adjusted = (
        b"<p>Net loss for the second quarter of 2025 was $3.0 million, compared with adjusted"
        b" net income of $1.1 million in the second quarter of 2024.</p>"
    )
    assert classify(adjusted, signs)["prior_ni"] == "label_only"


def test_rowspan_keeps_header_columns_aligned():
    html = b"""<p>(in millions)</p><table>
<tr><td rowspan="2">Unaudited</td><td colspan="2">Three Months Ended June 30,</td></tr>
<tr><td>2025</td><td>2024</td></tr>
<tr><td>Net income</td><td>5.2</td><td>(1.1)</td></tr></table>"""
    result = classify(html)
    assert result["current_ni"] == "stated" and result["prior_ni"] == "stated"


def test_money_forms_and_compact_comparatives():
    loss = dict(RECORD, current_ni="-3000000")
    for text in (
        b"Net income for the three months ended June 30, 2025 was USD 5.2 million.",
        b"Net income for the three months ended June 30, 2025 was 5.2 million USD.",
    ):
        assert classify(b"<p>" + text + b"</p>")["current_ni"] == "stated", text
    minus = b"<p>Net income for the three months ended June 30, 2025 was -$3.0 million.</p>"
    assert classify(minus, loss)["current_ni"] == "stated"
    compact = (
        b"<p>Net income for the three months ended June 30, 2025 and 2024 was $5.2 million"
        b" and $1.1 million, respectively.</p>"
    )
    assert classify(compact)["current_ni"] == "period_unverified"


def test_superscript_footnotes_and_source_order():
    html = table(
        [b"Three Months Ended June 30, 2025<sup>(a)</sup>"],
        [b"Net income<sup>1</sup>", b"5.2<sup>1</sup>"],
    )
    assert classify(html)["current_ni"] == "stated"
    layout = b"<table><tr><td>ACME Announces Earnings Release</td></tr></table><p>Body</p>"
    assert m.parse_document("html", layout)["text"].startswith("ACME Announces Earnings Release")


def test_statement_images_count_even_after_a_label():
    prose = b"<p>Net income rose.</p><p>Condensed Statements of Operations</p><img src='p2.jpg'>"
    assert classify(prose)["current_ni"] == "exhibit_unavailable"
    chart = b"<p>Strong cash flow and higher net income.</p><img src='chart.jpg'>"
    result = classify(chart)
    assert result["q_current_cfo"] == "not_found" and result["current_ni"] == "label_only"


def test_unreadable_candidate_keeps_an_ambiguous_component_possible():
    spec = m.comparison(RECORD)["current_ni"]
    readable = {
        "url": "a",
        "kind": "html",
        "sha256": "aa",
        "parsed": m.parse_document("html", table([b"Q2 2025"], [b"Net income", b"9.9"])),
    }
    unreadable = {"url": "b", "kind": "unsupported", "fetch_error": None}
    result, evidence = m.classify_component([readable, unreadable], spec, "net_income")
    assert result == "exhibit_unavailable"
    assert m.classify_component([readable], spec, "net_income")[0] == "label_only"


def test_layout_tables_month_year_headers_and_cfo_synonyms():
    layout = (
        b"<table><tr><td>Net income for the three months ended June 30, 2025 was $5.2 million."
        b"</td></tr></table>"
    )
    assert classify(layout)["current_ni"] == "stated"
    month_year = table([b"Three Months Ended June 2025"], [b"Net income", b"5.2"])
    assert classify(month_year)["current_ni"] == "stated"
    synonym = table([b"Six Months Ended June 30, 2025"], [b"Cash flow from operations", b"14.0"])
    assert classify(synonym)["q_current_cfo"] == "stated"
    continuing = table(
        [b"Three Months Ended June 30, 2025"], [b"Net income from continuing operations", b"5.2"]
    )
    assert classify(continuing)["current_ni"] == "not_found"


def test_currency_code_cells_and_header_currency_are_never_compared():
    header = [b"Three Months Ended June 30, 2025", b"", b""]
    before = table(header, [b"Net income", b"CAD", b"5.2"])
    after = table(header, [b"Net income", b"5.2", b"CAD"])
    words = table([b"Three Months Ended June 30, 2025 (Canadian dollars)"], [b"Net income", b"5.2"])
    for html in (before, after, words):
        assert classify(html)["current_ni"] == "currency_mismatch"


def test_image_inside_a_layout_table_takes_its_heading():
    html = (
        b"<table><tr><td>Consolidated Statements of Operations</td></tr>"
        b"<tr><td><img src='image1.jpg'></td></tr></table>"
    )
    assert classify(html)["current_ni"] == "exhibit_unavailable"


def test_table_evidence_records_the_row():
    doc = m.parse_document("html", release_html())
    spec = m.comparison(RECORD)["current_ni"]
    result, evidence = m.match_component(doc, spec, "net_income")
    assert result == "stated" and evidence[0]["row"] == 2 and evidence[0]["table"] == 0


def test_full_row_stacked_header_and_breaks_inside_cells():
    html = b"""<p>(in millions)</p><table>
<tr><td></td><td>Three Months Ended<br>June 30,</td><td></td></tr>
<tr><td></td><td>2025</td><td>2024</td></tr>
<tr><td>Net<br>income</td><td>5.2</td><td>(1.1)</td></tr>
<tr><td colspan="3">Six Months Ended June 30,</td></tr>
<tr><td></td><td>2025</td><td>2024</td></tr>
<tr><td>Net income</td><td>8.0</td><td>3.0</td></tr>
<tr><td>Net cash provided by operating activities</td><td>14.0</td><td>6.0</td></tr>
</table>"""
    result = classify(html)
    assert {result[n] for n in m.S_FLOW + m.Q_FLOW} == {"stated"}


def test_adjusted_amount_in_a_gaap_clause_is_not_credited():
    text = (
        b"<p>Net income was $4.0 million and adjusted net income was $5.2 million for the"
        b" three months ended June 30, 2025.</p>"
    )
    assert classify(text)["current_ni"] == "label_only"
    assert classify(text, dict(RECORD, current_ni="4000000"))["current_ni"] == "stated"


def test_a_scale_inferred_from_the_10q_value_is_unverified():
    bare = table([b"Three Months Ended June 30, 2025"], [b"Net income", b"5.2"], before=b"")
    assert classify(bare)["current_ni"] == "scale_unverified"
    units = table([b"Three Months Ended June 30, 2025"], [b"Net income", b"5,200,000"], before=b"")
    assert classify(units)["current_ni"] == "stated"


def test_table_wide_currency_and_mixed_duration_clauses():
    header = [b"Three Months Ended June 30, 2025"]
    cad = table(header, [b"Net income", b"5.2"], before=b"<p>(in millions of Canadian dollars)</p>")
    assert classify(cad)["current_ni"] == "currency_mismatch"
    prose = b"<p>Results reflect a stronger Canadian dollar.</p><p>(in millions)</p>"
    assert classify(table(header, [b"Net income", b"5.2"], before=prose))["current_ni"] == "stated"
    mixed = (
        b"<p>Net income for the second quarter of fiscal 2025 and first six months was $5.2"
        b" million and $8.0 million, respectively.</p>"
    )
    assert classify(mixed)["current_ni"] == "period_unverified"
    single = b"<p>Net income for the second quarter of fiscal year 2025 was $5.2 million.</p>"
    assert classify(single)["current_ni"] == "stated"


def test_other_metrics_columns_footnotes_and_parenthesised_codes():
    ebitda = (
        b"<p>Net income was $4.0 million and EBITDA was $5.2 million for the three months ended"
        b" June 30, 2025.</p>"
    )
    assert classify(ebitda)["current_ni"] == "label_only"
    html = b"""<table>
<tr><td></td><td>Three Months Ended June 30, 2025</td><td>Three Months Ended June 30, 2025</td></tr>
<tr><td></td><td>USD in millions</td><td>CAD in millions</td></tr>
<tr><td>Net income</td><td>5.2</td><td>7.1</td></tr></table>"""
    assert classify(html)["current_ni"] == "stated"
    assert m.parse_number("5.2(1)") == (Decimal("5.2"), 1, "")
    assert m.parse_number("(12)") == (Decimal(-12), 0, "")
    assert m.parse_number("(1,100)(2)") == (Decimal(-1100), 0, "")
    assert m.money_amounts("a loss (5.2 million USD) in total")[0][1] == Decimal("-5.2")


def test_narrative_evidence_records_label_and_period():
    text = b"<p>Net income for the three months ended June 30, 2025 was $5.2 million.</p>"
    doc = m.parse_document("html", text)
    result, evidence = m.match_component(doc, m.comparison(RECORD)["current_ni"], "net_income")
    assert result == "stated"
    assert evidence[0]["label"].startswith("Net income")
    assert evidence[0]["period"]["end"] == "2025-06-30"


def test_cell_units_own_column_periods_and_equivalent_quarter_dates():
    unit = table(
        [b"Three Months Ended June 30, 2025"], [b"Net income", b"$5.2 million"], before=b""
    )
    assert classify(unit)["current_ni"] == "stated"
    bare = table([b"Three Months Ended June 30, 2025", b"2025"], [b"Net income", b"9.9", b"5.2"])
    assert classify(bare)["current_ni"] == "period_unverified"
    same = (
        b"<p>For the second quarter of fiscal 2025 ended June 30, 2025, net income was $5.2"
        b" million and revenue was $100 million.</p>"
    )
    assert classify(same)["current_ni"] == "stated"


def test_sibling_measures_noncontrolling_phrases_and_images_over_currency():
    sibling = (
        b"<p>Net income was $4.0 million and cash flow from operations was $5.2 million for the"
        b" three months ended June 30, 2025.</p>"
    )
    assert classify(sibling)["current_ni"] == "label_only"
    minority = (
        b"<p>Net income attributable to noncontrolling interests for the three months ended"
        b" June 30, 2025 was $5.2 million.</p>"
    )
    assert classify(minority)["current_ni"] == "not_found"
    image = (
        b"<p>Net income for the three months ended June 30, 2025 was C$5.2 million.</p>"
        b"<p>Condensed Statements of Operations</p><img src='p.jpg'>"
    )
    assert classify(image)["current_ni"] == "exhibit_unavailable"


def test_evidence_keeps_matches_under_a_contradicting_period():
    doc = m.parse_document("html", release_html(ytd_ni=("5.2", "3.0")))
    docs = [{"url": "u", "kind": "html", "sha256": "s", "parsed": doc}]
    result, evidence = m.classify_component(docs, m.comparison(RECORD)["current_ni"], "net_income")
    assert result == "stated"
    assert {"stated", "different_period"} <= {e.get("result") for e in evidence}


def test_contradicting_dates_scripts_and_unit_precedence():
    wrong = (
        b"<p>Net income for the second quarter of fiscal 2025 ended September 30, 2025 was $5.2"
        b" million.</p>"
    )
    assert classify(wrong)["current_ni"] == "label_only"
    script = (
        b"<script>var s = 'Net income for the three months ended June 30, 2025 was $5.2 million.';"
        b"</script><p>Results</p>"
    )
    assert classify(script)["current_ni"] == "not_found"
    header = b"<tr><td>(in millions)</td><td>Three Months Ended June 30, 2025</td></tr>"
    rows = b"<tr><td>Net income</td><td>5.2</td></tr>"
    prose = b"<p>Revenue was $2.1 billion.</p><table>" + header + rows + b"</table>"
    assert classify(prose)["current_ni"] == "stated"
    only_prose = b"<p>Revenue was $2.1 billion.</p>" + table(
        [b"Three Months Ended June 30, 2025"], [b"Net income", b"5.2"], before=b""
    )
    assert classify(only_prose)["current_ni"] == "scale_unverified"


def test_other_dollar_prefixes_and_narrative_period_evidence():
    narrative = b"<p>Net income for the three months ended June 30, 2025 was A$5.2 million.</p>"
    assert classify(narrative)["current_ni"] == "currency_mismatch"
    usd = b"<p>Net income for the three months ended June 30, 2025 was US$5.2 million.</p>"
    assert classify(usd)["current_ni"] == "stated"
    header = [b"Three Months Ended June 30, 2025", b""]
    assert classify(table(header, [b"Net income", b"A$5.2"]))["current_ni"] == "currency_mismatch"
    split = table(header, [b"Net income", b"A$", b"5.2"])
    assert classify(split)["current_ni"] == "currency_mismatch"
    march = b"<p>Net income for the three months ended March 31, 2025 was $5.2 million.</p>"
    doc = m.parse_document("html", march)
    result, evidence = m.match_component(doc, m.comparison(RECORD)["current_ni"], "net_income")
    assert result == "label_only" and evidence[0]["result"] == "different_period"


def test_australian_markers_quarter_lists_and_sentence_boundaries():
    header = [b"Three Months Ended June 30, 2025", b""]
    for before in (b"<p>(in millions of Australian dollars)</p>", b"<p>(AUD in millions)</p>"):
        html = table([b"Three Months Ended June 30, 2025"], [b"Net income", b"5.2"], before=before)
        assert classify(html)["current_ni"] == "currency_mismatch", before
    trailing = table(header, [b"Net income", b"5.2", b"AUD"])
    assert classify(trailing)["current_ni"] == "currency_mismatch"
    quarters = (
        b"<p>For the first quarter of fiscal 2025 and the second quarter of fiscal 2025, net"
        b" income was $5.2 million.</p>"
    )
    assert classify(quarters)["current_ni"] == "period_unverified"
    quoted = (
        b'<p>Net income for the three months ended June 30, 2025 was $4.0 million. "Net income'
        b' was $5.2 million."</p>'
    )
    assert classify(quoted)["current_ni"] == "period_unverified"
    september = dict(RECORD, current_start="2025-07-01", current_end="2025-09-30")
    sept = b"<p>Net income for the three months ended Sept. 30, 2025 was $5.2 million.</p>"
    assert classify(sept, september)["current_ni"] == "stated"


def test_reversed_currency_phrases_closing_quotes_split_cells_and_between_codes():
    header = [b"Three Months Ended June 30, 2025"]
    for before, value in (
        (b"<p>(Canadian dollars in millions)</p>", b"5.2"),
        (b"<p>(Australian dollars, in thousands)</p>", b"5,200"),
    ):
        html = table(header, [b"Net income", value], before=before)
        assert classify(html)["current_ni"] == "currency_mismatch", before
    quoted = (
        b'<p>"Net income for the three months ended June 30, 2025 was $4.0 million." Net income'
        b" was $5.2 million.</p>"
    )
    assert classify(quoted)["current_ni"] == "period_unverified"
    dated = (
        b"<p>For the first quarter of fiscal 2025 ended March 31, 2025 and the second quarter of"
        b" fiscal 2025 ended June 30, 2025, net income was $5.2 million.</p>"
    )
    assert classify(dated)["current_ni"] == "period_unverified"
    split = (
        b"<table><tr><td>Net income for the three months ended June 30, 2025 was</td>"
        b"<td>$5.2 million</td></tr></table>"
    )
    assert classify(split)["current_ni"] == "stated"
    columns = [b"Three Months Ended June 30, 2025", b"", b"Three Months Ended June 30, 2024", b""]
    between = table(columns, [b"Net income", b"5.2", b"AUD", b"4.0", b"USD"])
    assert classify(between)["current_ni"] == "currency_mismatch"

    def merged(*texts):
        cells = [{"text": t, "col": i, "span": 1} for i, t in enumerate(texts)]
        return [c["text"] for c in m._merge(cells)]

    assert merged("Net income", "5.2", "AUD", "4.0", "USD") == ["5.2 AUD", "4.0 USD"]
    assert merged("Net income", "USD", "5.2", "AUD", "4.0") == ["USD 5.2", "AUD 4.0"]
    assert merged("Net income", "5.2", "AUD", "4.0") == ["5.2 AUD", "AUD 4.0"]
    assert merged("Net income", "$", "5.2", "$", "4.0") == ["$5.2", "$4.0"]
    assert merged("Net income", "US$", "5.2", "US$", "4.0") == ["US$5.2", "US$4.0"]


def test_prose_rows_join_their_cells_and_table_wide_header_currency():
    split = (
        b"<table><tr><td>Net income for the three months ended June 30, 2025</td>"
        b"<td>was $5.2 million.</td></tr></table>"
    )
    assert classify(split)["current_ni"] == "stated"
    wide = b"""<table>
<tr><td>CAD in millions</td><td>Three Months Ended June 30, 2025</td></tr>
<tr><td>Net income</td><td>5.2</td></tr></table>"""
    assert classify(wide)["current_ni"] == "currency_mismatch"
    usd = wide.replace(b"CAD in millions", b"(in millions)")
    assert classify(usd)["current_ni"] == "stated"


def test_new_measures_dated_quarters_nested_context_and_one_column_periods():
    tax = (
        b"<p>Net income was $4.0 million and income tax expense was $5.2 million for the three"
        b" months ended June 30, 2025.</p>"
    )
    assert classify(tax)["current_ni"] == "label_only"
    carried = b"<p>Net income for the three months ended June 30, 2025 rose; R&amp;D expense was"
    carried += b" $5.2 million for the three months ended June 30, 2025.</p>"
    assert classify(carried)["current_ni"] == "label_only"
    respectively = (
        b"<p>Net income was $5.2 million and $4.0 million for the three months ended June 30,"
        b" 2025 and 2024, respectively.</p>"
    )
    assert classify(respectively)["current_ni"] == "period_unverified"
    dated = (
        b"<p>For the second quarter of fiscal 2025, the periods ended March 31, 2025 and June 30,"
        b" 2025 had net income of $5.2 million.</p>"
    )
    assert classify(dated)["current_ni"] == "period_unverified"
    nested = b"""<table><tr><td>(in millions of Canadian dollars)<table>
<tr><td></td><td>Three Months Ended June 30, 2025</td></tr>
<tr><td>Net income</td><td>5.2</td></tr></table></td></tr></table>"""
    assert classify(nested)["current_ni"] == "currency_mismatch"
    one = b"<p>Three Months Ended June 30, 2025 (in millions)</p><table>"
    one += b"<tr><td>Net income</td><td>5.2</td></tr></table>"
    assert classify(one)["current_ni"] == "stated"
    two = one.replace(b"<td>5.2</td>", b"<td>5.2</td><td>4.0</td>")
    assert classify(two)["current_ni"] == "period_unverified"


def test_singleton_currency_headers_and_mismatch_evidence_periods():
    html = b"""<p>(in millions)</p><table>
<tr><td></td><td>CAD</td><td></td></tr>
<tr><td></td><td>Three Months Ended June 30, 2025</td><td>Three Months Ended June 30, 2025</td></tr>
<tr><td>Net income</td><td>7.1</td><td>5.2</td></tr></table>"""
    assert classify(html)["current_ni"] == "stated"
    cad = table([b"Three Months Ended June 30, 2025", b""], [b"Net income", b"5.2", b"CAD"])
    doc = m.parse_document("html", cad)
    result, evidence = m.match_component(doc, m.comparison(RECORD)["current_ni"], "net_income")
    assert result == "currency_mismatch" and evidence[0]["period"]["end"] == "2025-06-30"


def test_trailing_qualifiers_non_gaap_columns_fy_quarters_images_and_forecasts():
    period = b" for the three months ended June 30, 2025"
    for tail in (b" attributable to noncontrolling interests", b" from continuing operations"):
        html = b"<p>Net income" + period + b" was $5.2 million" + tail + b".</p>"
        assert classify(html)["current_ni"] == "label_only", tail
    per_share = b"<p>Net income" + period + b" was $5.2 million, or 52 cents per diluted share.</p>"
    assert classify(per_share)["current_ni"] == "stated"
    column = table([b"Non-GAAP Three Months Ended June 30, 2025"], [b"Net income", b"5.2"])
    assert classify(column)["current_ni"] == "label_only"
    for phrase in (b"Q2 FY2025", b"FY2025 Q2", b"Q2 FY25", b"fiscal 2025 second quarter"):
        html = b"<p>Net income for " + phrase + b" was $5.2 million.</p>"
        assert classify(html)["current_ni"] == "stated", phrase
    other = b"<p>Net income for Q1 FY2025 was $5.2 million.</p>"
    assert classify(other)["current_ni"] == "label_only"  # a different quarter is not counted
    for name, component in (
        (b"income_statement.png", "current_ni"),
        (b"Income%20Statement.jpg", "current_ni"),
        (b"cash-flow-statement.png", "q_current_cfo"),
        (b"balance-sheet.jpg", "prior_fy_assets"),
    ):
        image = classify(b"<p>Results.</p><img src='" + name + b"'>")
        assert image[component] == "exhibit_unavailable", name
    for text in (
        b"<p>We forecast net income"
        + period.replace(b"ended", b"ending")
        + b" of $5.2 million.</p>",
        b"<p>Net income" + period + b" is expected to be $5.2 million.</p>",
    ):
        assert classify(text)["current_ni"] == "label_only", text


def test_quarter_words_lists_and_partial_dates():
    first = b"<p>Net income was first reported in June 2025 as $5.2 million.</p>"
    q1 = dict(RECORD, fiscal_period="Q1")
    assert classify(first, q1)["current_ni"] == "period_unverified"
    months = (
        b"<p>For Q2 FY2025, the periods June 2025 and March 2025 had net income of $5.2"
        b" million.</p>"
    )
    assert classify(months)["current_ni"] == "period_unverified"
    for listed in (b"the first and second quarters of 2025", b"Q1 and Q2 2025"):
        html = b"<p>Net income for " + listed + b" was $5.2 million.</p>"
        assert classify(html)["current_ni"] == "period_unverified", listed
    per_share = table(
        [b"Three Months Ended June 30, 2025"],
        [b"Net income", b"5.2"],
        before=b"<p>(in millions, except per share data)</p>",
    )
    assert classify(per_share)["current_ni"] == "stated"


def test_ambiguous_or_missing_duration_is_period_unverified():
    # A dated column whose duration cannot be resolved is unverified, never silently dropped.
    both = b"<p>Three and six months ended (in millions)</p>"
    html = table([b"June 30, 2025"], [b"Net income", b"5.2"], before=both)
    assert classify(html)["current_ni"] == "period_unverified"
    bare = table([b"June 30, 2025"], [b"Net income", b"5.2"])
    assert classify(bare)["current_ni"] == "period_unverified"
    quarter = table([b"Three Months Ended June 30, 2025"], [b"Total assets", b"1,400"])
    assert classify(quarter, dict(RECORD, prior_fy_end="2025-06-30"))["prior_fy_assets"] == (
        "period_unverified"
    )


def test_other_currency_is_never_compared():
    html = table([b"Three Months Ended June 30, 2025"], [b"Net income", b"C$5.2"])
    assert classify(html)["current_ni"] == "currency_mismatch"


def test_image_dependence_is_per_component():
    statement = b'<p>Results</p><img alt="Statements of Cash Flows" src="cf.jpg">'
    logo = b'<img alt="ACME logo" src="logo.jpg"><p>Results</p>'
    assert classify(statement)["q_current_cfo"] == "exhibit_unavailable"
    assert classify(statement)["current_ni"] == "not_found"
    assert classify(logo)["q_current_cfo"] == "not_found"


def test_narrative_sentences_need_their_own_period():
    loss = dict(RECORD, current_ni="-3000000")
    stated = b"<p>The net loss for the three months ended June 30, 2025 was $3.0 million.</p>"
    vague = b"<p>The company reported a net loss of $3.0 million.</p>"
    other = b"<p>The net loss for the three months ended March 31, 2025 was $3.0 million.</p>"
    excluded = (
        b"<p>Net income excluding special items for the quarter ended June 30, 2025"
        b" was $5.2 million.</p>"
    )
    assert classify(stated, loss)["current_ni"] == "stated"
    assert classify(vague, loss)["current_ni"] == "period_unverified"
    assert classify(other, loss)["current_ni"] == "label_only"
    assert classify(excluded)["current_ni"] == "not_found"


def test_fiscal_quarter_phrase_and_prior_year():
    prior = dict(RECORD, prior_ni="4100000")
    html = b"<p>Net income in the second quarter of fiscal 2024 was $4.1 million.</p>"
    assert classify(html, prior)["prior_ni"] == "stated"
    assert classify(html, prior)["current_ni"] == "label_only"


def test_plain_text_exhibit_tables():
    text = b"""ACME CORP (in thousands)
                Three Months Ended June 30, 2025    Three Months Ended June 30, 2024
Net income                5,200                               (1,100)
"""
    result = classify(text, kind="text")
    assert result["current_ni"] == "stated" and result["prior_ni"] == "stated"


def at(*placed):
    """One plain-text line with each text right-aligned to end at its column."""
    line = ""
    for end, text in placed:
        line = line.ljust(end - len(text)) + text
    return line


def test_plain_text_tables_align_by_position_and_split_on_new_headers():
    lines = [
        "ACME CORP",
        "CONDENSED STATEMENTS OF OPERATIONS (in thousands)",
        at((48, "Three Months Ended"), (74, "Six Months Ended")),
        at((43, "June 30,"), (71, "June 30,")),
        at((38, "2025"), (52, "2024"), (66, "2025"), (80, "2024")),
        at((38, "--------"), (52, "--------"), (66, "--------"), (80, "--------")),
        "Revenues:",
        at((9, "  Product"), (38, "9,000"), (52, "8,000"), (66, "17,000"), (80, "15,000")),
        at((10, "Net income"), (31, "$"), (38, "5,200"), (52, "$ (1,100)"), (59, "$")),
        "",
        "BALANCE SHEETS (in thousands)",
        at((40, "June 30, 2025"), (60, "December 31, 2024")),
        at((12, "Total assets"), (40, "1,500,000"), (60, "1,400,000")),
    ]
    lines[8] += at((66 - 59, "8,000"), (80 - 59, "$ 3,000"))
    doc = m.parse_document("text", "\n".join(lines).encode())
    assert len(doc["tables"]) == 2
    result = classify("\n".join(lines).encode(), kind="text")
    for name in ("current_ni", "prior_ni", "q_current_ni", "q_prior_ni", "prior_fy_assets"):
        assert result[name] == "stated", name
    assert doc["tables"][1]["context"] == "BALANCE SHEETS (in thousands)"


def test_numbers_and_periods():
    assert m.parse_number("1,234") == (Decimal(1234), 0, "")
    assert m.parse_number("—") == (Decimal(0), 0, "")
    assert m.parse_number("12%") is None
    assert m.parse_number("C$5")[2] == "other"
    assert m.parse_period("June 30, 2025")["instant"]
    period = m.parse_period("2025", "Three Months Ended June 30")
    assert period["months"] == 3 and period["end"] == date(2025, 6, 30)
    assert m.parse_period("June 30, 2025 December 31, 2024")["end"] is None
    assert m.parse_period("Three and Six Months Ended June 30, 2025")["months"] is None
    assert not m.parse_period("Three and Six Months Ended June 30, 2025")["instant"]


def test_ytd_header_takes_the_10q_year_to_date_length():
    html = table(
        [b"Year to date June 30, 2025"],
        [b"Net income", b"5.2"],
        [b"Net cash from operating activities", b"14.0"],
    )
    result = classify(html)
    assert result["current_ni"] == "label_only" and result["q_current_cfo"] == "stated"
    q1 = dict(
        RECORD,
        fiscal_period="Q1",
        current_start="2025-04-01",
        q_current_start="2025-04-01",
        q_prior_start="2024-04-01",
    )
    assert classify(html, q1)["current_ni"] == "stated"


def test_forward_table_labels_and_declared_table_currency():
    header = [b"Three Months Ended June 30, 2025"]
    for label in (b"Estimated net income", b"Net income guidance", b"Projected net income"):
        assert classify(table(header, [label, b"5.2"]))["current_ni"] == "label_only", label
    outlook = table([b"Outlook for the Three Months Ended June 30, 2025"], [b"Net income", b"5.2"])
    assert classify(outlook)["current_ni"] == "label_only"
    for before in (
        b"<p>All amounts are in CAD.</p><p>(in millions)</p>",
        b"<p>(in millions) CAD</p>",
        b"<p>Amounts are expressed in Canadian dollars (in millions)</p>",
    ):
        html = table(header, [b"Net income", b"5.2"], before=before)
        assert classify(html)["current_ni"] == "currency_mismatch", before


def test_table_titles_other_currencies_and_guidance_before_labels():
    header = [b"Three Months Ended June 30, 2025"]
    for before in (
        b"<p>Projected Financial Results (in millions)</p>",
        b"<p>Reconciliation of Non-GAAP Measures (in millions)</p>",
    ):
        html = table(header, [b"Net income", b"5.2"], before=before)
        assert classify(html)["current_ni"] == "label_only", before
    for before in (
        b"<p>(in millions of Japanese yen)</p>",
        b"<p>(JPY in millions)</p>",
        b"<p>(in millions of Swiss francs)</p>",
    ):
        html = table(header, [b"Net income", b"5.2"], before=before)
        assert classify(html)["current_ni"] == "currency_mismatch", before
    yen = "<p>Net income for the three months ended June 30, 2025 was \u00a55.2 million.</p>"
    assert classify(yen.encode())["current_ni"] == "currency_mismatch"
    guidance = b"<p>Our guidance: net income for Q2 FY2025 was $5.2 million.</p>"
    assert classify(guidance)["current_ni"] == "label_only"


def test_excluded_column_headers_qualified_totals_and_colon_subjects():
    for column in (
        b"Core Three Months Ended June 30, 2025",
        b"Per Share Three Months Ended June 30, 2025",
    ):
        assert classify(table([column], [b"Net income", b"5.2"]))["current_ni"] == "label_only"
    unit = b"""<table>
<tr><td>(in millions, except per share data)</td><td>Three Months Ended June 30, 2025</td></tr>
<tr><td>Net income</td><td>5.2</td></tr></table>"""
    assert classify(unit)["current_ni"] == "stated"
    year_end = [b"December 31, 2024"]
    assert classify(table(year_end, [b"Total assets", b"1,400"]))["prior_fy_assets"] == "stated"
    for label in (b"Average total assets", b"Total assets under management"):
        result = classify(table(year_end, [label, b"1,400"]))["prior_fy_assets"]
        assert result in ("not_found", "label_only"), label
    period = b"<p>Net income for the three months ended June 30, 2025: "
    colon = period + b"$4.0 million and income tax expense: $5.2 million.</p>"
    assert classify(colon)["current_ni"] == "label_only"
    assert classify(period + b"$5.2 million.</p>")["current_ni"] == "stated"


def test_cash_flow_scope_bound_prefix_qualifiers_and_mixed_header_dates():
    six = [b"Six Months Ended June 30, 2025"]
    for label in (
        b"Net cash generated from financing operations",
        b"Cash provided by investing operations",
    ):
        result = classify(table(six, [label, b"14.0"]))["q_current_cfo"]
        assert result in ("not_found", "label_only"), label
    assert (
        classify(table(six, [b"Cash flow from operations", b"14.0"]))["q_current_cfo"] == "stated"
    )
    bound = b"<p>Adjusted EBITDA improved and net income for Q2 FY2025 was $5.2 million.</p>"
    assert classify(bound)["current_ni"] == "stated"
    adjusted = b"<p>Adjusted net income for Q2 FY2025 was $5.2 million.</p>"
    assert classify(adjusted)["current_ni"] in ("not_found", "label_only")
    mixed = table([b"Three Months Ended June 30, 2025 and March 2025"], [b"Net income", b"5.2"])
    assert classify(mixed)["current_ni"] == "period_unverified"
    assert m.parse_period("Three Months Ended June 30, 2025 and March 31")["end"] is None


def test_change_verbs_parenthesised_dollars_open_cells_and_trailing_codes():
    tax = b"<p>Net income for Q2 FY2025 was $4.0 million and income tax expense increased to"
    tax += b" $5.2 million.</p>"
    assert classify(tax)["current_ni"] == "label_only"
    rose = b"<p>Net income for Q2 FY2025 increased to $5.2 million.</p>"
    assert classify(rose)["current_ni"] == "stated"
    for money in (b"$(1.1) million", b"$ (1.1) million"):
        html = b"<p>Net loss for the three months ended June 30, 2024 was " + money + b".</p>"
        assert classify(html)["prior_ni"] == "stated", money
    implicit = b"""<p>(in millions)</p><table><tr><td></td><td>Three Months Ended June 30, 2025
<tr><td>Net income<td>5.2</table>"""
    assert classify(implicit)["current_ni"] == "stated"
    period = b"<p>Net income for the three months ended June 30, 2025 was $5.2 million "
    assert classify(period + b"CAD.</p>")["current_ni"] == "currency_mismatch"
    assert classify(period + b"USD.</p>")["current_ni"] == "stated"


def test_excluded_titles_colon_qualifiers_and_change_amounts():
    header = [b"Three Months Ended June 30, 2025"]
    core = table(
        header, [b"Net income", b"5.2"], before=b"<p>Core Financial Results (in millions)</p>"
    )
    assert classify(core)["current_ni"] == "label_only"
    unit = b"<table><tr><td>(In thousands, except share and per share data)</td>"
    unit += b"<td>Three Months Ended June 30, 2025</td></tr>"
    unit += b"<tr><td>Net income</td><td>5,200</td></tr></table>"
    assert classify(unit)["current_ni"] == "stated"
    for qualifier in (b"Adjusted", b"Non-GAAP"):
        html = b"<p>" + qualifier + b": net income for Q2 FY2025 was $5.2 million.</p>"
        assert classify(html)["current_ni"] in ("not_found", "label_only"), qualifier
    for change in (
        b"increased by $5.2 million",
        b"saw an increase of $5.2 million",
        b"was up $5.2 million",
    ):
        html = b"<p>Net income for Q2 FY2025 " + change + b".</p>"
        assert classify(html)["current_ni"] == "label_only", change


def test_change_rows_and_columns_more_currencies_and_fiscal_quarter_headers():
    header = [b"Three Months Ended June 30, 2025"]
    assert classify(table(header, [b"Increase in net income", b"5.2"]))["current_ni"] in (
        "not_found",
        "label_only",
    )
    change = b"""<p>(in millions)</p><table>
<tr><td></td><td colspan="2">Three Months Ended June 30, 2025</td></tr>
<tr><td></td><td>Amount</td><td>Change</td></tr>
<tr><td>Net income</td><td>9.9</td><td>5.2</td></tr></table>"""
    assert classify(change)["current_ni"] == "label_only"
    for before in (
        b"<p>(in millions of Russian rubles)</p>",
        b"<p>(TRY in millions)</p>",
        b"<p>(in millions of Turkish lira)</p>",
    ):
        html = table(header, [b"Net income", b"5.2"], before=before)
        assert classify(html)["current_ni"] == "currency_mismatch", before
    for quarter in (b"Q2 FY2025", b"FY2025 Q2", b"Second quarter of fiscal 2025"):
        assert classify(table([quarter], [b"Net income", b"5.2"]))["current_ni"] == "stated"
    other = classify(table([b"Q1 FY2025"], [b"Net income", b"5.2"]))["current_ni"]
    assert other == "label_only"  # another fiscal quarter: a different period, dropped
    both = table([b"Q2 FY2025", b"Q2 FY2024"], [b"Net income", b"5.2", b"(1.1)"])
    assert classify(both)["prior_ni"] == "stated"


def test_elliptical_years_modal_forecasts_label_currency_and_footnote_cells():
    both = table([b"Three Months Ended June 30, 2025 and 2024"], [b"Net income", b"5.2"])
    assert classify(both)["current_ni"] == "period_unverified"
    for verb in (b"will total", b"will reach", b"would be", b"is going to be", b"may reach"):
        html = b"<p>Net income for the second quarter of fiscal 2025 %s $5.2 million.</p>" % verb
        assert classify(html)["current_ni"] == "label_only", verb
    may = b"<p>Net income for the quarter ended May 31, 2025 was $5.2 million.</p>"
    assert m.PROSPECTIVE.search(may.decode()) is None  # the month is not a modal
    header = [b"Three Months Ended June 30, 2025"]
    coded = table(header, [b"Net income (CAD millions)", b"5.2"])
    assert classify(coded)["current_ni"] == "currency_mismatch"
    loss = dict(RECORD, current_ni="-1000000")
    note = b"""<p>(in millions)</p><table>
<tr><td></td><td colspan="2">Three Months Ended June 30, 2025</td></tr>
<tr><td>Net loss</td><td>(1)</td><td>(5.2)</td></tr></table>"""
    assert classify(note, record=loss)["current_ni"] == "label_only"
    after = table(header, [b"Net loss", b"(5.2)", b"(1)"])
    assert classify(after, record=loss)["current_ni"] == "label_only"
    marked = table(header, [b"Net loss", b"$", b"(1)"])  # a currency mark makes it a value
    assert classify(marked, record=loss)["current_ni"] == "stated"


def test_leading_spaced_codes_copula_less_declarations_and_annotation_columns():
    for money in (b"CAD $5.2 million", b"(CAD $5.2 million)", b"Canadian dollars $5.2 million"):
        html = b"<p>Net income for the second quarter of fiscal 2025 was %s.</p>" % money
        assert classify(html)["current_ni"] == "currency_mismatch", money
    usd = b"<p>Net income for the second quarter of fiscal 2025 was USD $5.2 million.</p>"
    assert classify(usd)["current_ni"] == "stated"
    header = [b"Three Months Ended June 30, 2025"]
    for before in (b"<p>All amounts in Canadian dollars</p>", b"<p>Figures in EUR</p>"):
        html = table(header, [b"Net income", b"$5,200,000"], before=before)
        assert classify(html)["current_ni"] == "currency_mismatch", before
    for extra in (b"<td>*</td>", b"<td>12%</td>", b""):
        one = (
            b"""<p>Three Months Ended June 30, 2025 (in millions)</p><table>
<tr><td>Net income</td><td>5.2</td>%s</tr></table>"""
            % extra
        )
        assert classify(one)["current_ni"] == "stated", extra
    two = b"""<p>Three Months Ended June 30, 2025 (in millions)</p><table>
<tr><td>Net income</td><td>5.2</td><td>4.0</td></tr></table>"""
    assert classify(two)["current_ni"] == "period_unverified"  # two columns: neither is known


def test_ambiguous_fiscal_headers_present_tense_forecasts_and_unspanned_sections():
    for header in (b"Q2 and Q3 FY2025", b"Q2 FY2025 June 30, 2025 and March 31, 2025"):
        html = table([header], [b"Net income", b"5.2"])
        assert classify(html)["current_ni"] == "period_unverified", header
    for sentence in (
        b"The company projects net income for the quarter ended June 30, 2025 of $5.2 million.",
        b"Net income for the three months ended June 30, 2025 is targeted at $5.2 million.",
    ):
        assert classify(b"<p>" + sentence + b"</p>")["current_ni"] == "label_only", sentence

    def stacked(section):
        return (
            b"""<p>(in millions)</p><table>
<tr><td></td><td>Three Months Ended June 30, 2025</td></tr>
<tr><td>Revenue</td><td>90.0</td></tr>
<tr><td>%s</td><td></td></tr>
<tr><td>Net income</td><td>5.2</td></tr></table>"""
            % section
        )

    # a lone, unspanned period cell starts a new section; a label naming only a year does not
    assert classify(stacked(b"Six Months Ended June 30, 2025"))["current_ni"] == "label_only"
    assert classify(stacked(b"2024 Restructuring Plan:"))["current_ni"] == "stated"


def test_embedded_items_and_plain_text_period_sections():
    for sentence in (
        b"Net income for Q2 FY2025 included a $5.2 million tax benefit.",
        b"Net income for Q2 FY2025 reflects income tax expense of $5.2 million.",
    ):
        assert classify(b"<p>" + sentence + b"</p>")["current_ni"] == "label_only", sentence
    for sentence in (
        b"Net income for Q2 FY2025, which included a tax benefit, was $5.2 million.",
        b"Net income for Q2 FY2025 increased by 10% to $5.2 million.",
    ):
        assert classify(b"<p>" + sentence + b"</p>")["current_ni"] == "stated", sentence
    text = b"""ACME Corp
(in millions)
                                  Three Months Ended June 30, 2025
Revenue                                  90.0
Six Months Ended June 30, 2025
Net income                                5.2
"""
    assert classify(text, kind="text")["current_ni"] == "label_only"  # a six-month value


def test_in_currency_titles_over_unit_lines_years_colons_and_prefixed_changes():
    def prose(sentence):
        return classify(b"<p>" + sentence + b"</p>")["current_ni"]

    q2 = b"Net income for Q2 FY2025 "
    assert prose(q2 + b"was $5.2 million in Canadian dollars.") == "currency_mismatch"
    assert prose(q2 + b"was $5.2 million in USD.") == "stated"

    def titled(title):
        return (
            b"<p>%s</p><p>(in millions)</p><table><tr><td></td>"
            b"<td>Three Months Ended June 30, 2025</td></tr>"
            b"<tr><td>Net income</td><td>5.2</td></tr></table>" % title
        )

    assert classify(titled(b"Core Financial Results"))["current_ni"] == "label_only"
    assert classify(titled(b"Condensed Statements of Operations"))["current_ni"] == "stated"
    text = b"""Core Financial Results
(in millions)
                                  Three Months Ended June 30, 2025
Net income                                5.2
"""
    assert classify(text, kind="text")["current_ni"] == "label_only"
    second = b"Net income for the second quarter of fiscal 2025 "
    assert prose(second + b"and fiscal 2024 was $5.2 million.") == "period_unverified"
    assert prose(second + b"ended June 30, 2025 was $5.2 million.") == "stated"
    assert prose(q2 + b": income tax expense was $5.2 million.") == "label_only"
    assert prose(q2 + b": $5.2 million.") == "stated"
    for change in (b"The increase in net income", b"Growth in the Company's net income"):
        assert prose(change + b" for Q2 FY2025 was $5.2 million.") == "not_found", change
    assert prose(b"Despite a decline in revenue net income for Q2 FY2025 was $5.2 million.") == (
        "stated"
    )


def test_more_currency_forms_shared_years_changes_bases_and_probable_forecasts():
    def prose(sentence):
        return classify(b"<p>Net income for Q2 FY2025 " + sentence + b"</p>")["current_ni"]

    assert prose(b"was $5.2 million (CAD).") == "currency_mismatch"
    assert prose(b"was Canadian $5.2 million.") == "currency_mismatch"
    assert prose(b"was $5.2 million (USD).") == "stated"
    september = dict(RECORD, current_start="2025-07-01", current_end="2025-09-30")
    for header, expected in (
        (b"Three Months Ended June and September 2025", "period_unverified"),
        (b"Three Months Ended September 2025", "stated"),
    ):
        html = table([header], [b"Net income", b"5.2"])
        assert classify(html, record=september)["current_ni"] == expected, header
    growth = b"""<p>(in millions)</p><table>
<tr><td></td><td colspan="2">Q2 FY2025</td></tr>
<tr><td></td><td>Amount</td><td>Growth</td></tr>
<tr><td>Net income</td><td>9.9</td><td>5.2</td></tr></table>"""
    assert classify(growth)["current_ni"] == "label_only"
    for sentence in (
        b"increased $5.2 million.",
        b"fell $5.2 million.",
        b"increased to $6.0 million from $5.2 million.",
        b"is likely to reach $5.2 million.",
    ):
        assert prose(sentence) == "label_only", sentence
    assert prose(b"rose to $5.2 million.") == "stated"
    assert prose(b"improved from $4.1 million to $5.2 million.") == "stated"
    header = [b"Three Months Ended June 30, 2025"]
    for label in (b"Normalized net income", b"Underlying net earnings"):
        assert classify(table(header, [label, b"5.2"]))["current_ni"] == "not_found", label


def test_pretax_and_common_shareholder_labels_and_causal_subjects():
    header = [b"Three Months Ended June 30, 2025"]
    for label in (
        b"Pre-tax net income",
        b"Pretax net income",
        b"Net income available to common shareholders",
    ):
        assert classify(table(header, [label, b"5.2"]))["current_ni"] == "not_found", label

    def prose(sentence):
        return classify(b"<p>Net income for Q2 FY2025 " + sentence + b"</p>")["current_ni"]

    for sentence in (
        b"declined primarily because income tax expense was $5.2 million.",
        b"declined as restructuring charges were $5.2 million.",
    ):
        assert prose(sentence) == "label_only", sentence
    assert prose(b"as reported was $5.2 million.") == "stated"


def test_suffix_changes_list_separators_company_suffixes_open_tables_and_sections():
    header = [b"Three Months Ended June 30, 2025"]
    for label in (b"Net income change", b"Net income increase", b"Net income growth"):
        assert classify(table(header, [label, b"5.2"]))["current_ni"] == "not_found", label
    change = b"<p>Net income change for Q2 FY2025 was $5.2 million.</p>"
    assert classify(change)["current_ni"] == "not_found"
    ytd = dict(RECORD, q_current_ni="5200000")
    for both in (
        b"Three/Six Months Ended June 30, 2025",
        b"Three & Six Months Ended June 30, 2025",
    ):
        html = table([both], [b"Net income", b"5.2"])
        assert classify(html, record=ytd)["q_current_ni"] == "period_unverified", both
    for quarters in (b"Q2/Q3 FY2025", b"Q2 & Q3 FY2025"):
        html = table([quarters], [b"Net income", b"5.2"])
        assert classify(html)["current_ni"] == "period_unverified", quarters
    ended = b"<p>Net income for Q2 FY2025 declined at Acme Inc. Income tax expense for Q2 FY2025"
    assert classify(ended + b" was $5.2 million.</p>")["current_ni"] == "label_only"
    named = b"<p>Acme Inc. (NASDAQ: ACME) reported net income for Q2 FY2025 of $5.2 million.</p>"
    assert classify(named)["current_ni"] == "stated"
    unclosed = b"<p>(in millions)</p><table><tr><td></td><td>Three Months Ended June 30, 2025"
    unclosed += b"</td></tr><tr><td>Net income</td><td>5.2</td></tr>"
    assert classify(unclosed)["current_ni"] == "stated"  # the table is read at the end of input

    def sectioned(heading):
        return (
            b"""<p>(in millions)</p><table>
<tr><td></td><td>Three Months Ended June 30, 2025</td></tr>
<tr><td>Revenue</td><td>90.0</td></tr>
<tr><td colspan="2">%s</td></tr>
<tr><td>Net income</td><td>5.2</td></tr></table>"""
            % heading
        )

    assert classify(sectioned(b"Non-GAAP Measures"))["current_ni"] == "label_only"
    assert classify(sectioned(b"Operating activities:"))["current_ni"] == "stated"
    assert classify(sectioned(b"Discontinued operations:"))["current_ni"] == "stated"  # a total
    text = b"""(in millions)
                                  Three Months Ended June 30, 2025
Revenue                                  90.0
Non-GAAP Measures
Net income                                5.2
"""
    assert classify(text, kind="text")["current_ni"] == "label_only"
    wrapped = b"""(in millions)
                                  Three Months Ended June 30, 2025
Revenue                                  90.0
Net income excluding
special items                             1.0
Net income                                5.2
"""
    assert (
        classify(wrapped, kind="text")["current_ni"] == "stated"
    )  # a wrapped label, not a heading


def test_mismatched_quarters_tax_labels_result_wording_and_abbreviation_endings():
    for quarter in (b"Q3 FY2025", b"Q2 FY2024"):
        html = table([quarter], [b"Net income", b"5.2"])
        assert classify(html)["current_ni"] == "label_only", quarter  # a different period
    header = [b"Three Months Ended June 30, 2025"]
    for label in (b"Net income taxes paid", b"Net income tax expense"):
        assert classify(table(header, [label, b"5.2"]))["current_ni"] == "not_found", label

    def prose(sentence):
        return classify(b"<p>" + sentence + b"</p>")["current_ni"]

    q2 = b"Net income for Q2 FY2025 "
    for sentence in (
        q2 + b"resulted primarily from an income tax benefit of $5.2 million.",
        q2 + b"stemmed from an income tax benefit of $5.2 million.",
        q2 + b"was driven primarily by a $5.2 million tax benefit.",
        b"Net income declined in the U.S. Income tax expense for Q2 FY2025 was $5.2 million.",
    ):
        assert prose(sentence) == "label_only", sentence
    assert prose(q2 + b"in the U.S. was $5.2 million.") == "stated"
    level = b"Net income for Q2 FY2025, which resulted from a tax benefit, was $5.2 million."
    assert prose(level) == "stated"  # a level verb follows the inclusion word
    dated = "Net income for the quarter ended Sept. 30, 2025 was $5.2 million at Acme Inc. today."
    assert list(m.sentences([dated])) == [dated]  # no capital letter after the abbreviations


def test_stacked_metadata_titles_midpoints_bounds_ranges_and_note_columns():
    core = b"<p>Core Financial Results</p><p>(Unaudited)</p><p>(in millions)</p><table><tr><td>"
    core += b"</td><td>Three Months Ended June 30, 2025</td></tr><tr><td>Net income</td><td>5.2"
    core += b"</td></tr></table>"
    assert classify(core)["current_ni"] == "label_only"
    header = [b"Three Months Ended June 30, 2025"]
    whole = table(header, [b"Net income", b"5"])
    assert classify(whole, record=dict(RECORD, current_ni="5500000"))["current_ni"] == "label_only"
    assert classify(whole, record=dict(RECORD, current_ni="5400000"))["current_ni"] == "stated"

    def prose(sentence):
        return classify(b"<p>Net income for Q2 FY2025 " + sentence + b"</p>")["current_ni"]

    for sentence in (
        b"was less than $5.2 million.",
        b"was between $4.8 million and $5.2 million.",
        b"was $5.2 million to $6.0 million.",
    ):
        assert prose(sentence) == "label_only", sentence
    assert prose(b"improved from $4.1 million to $5.2 million.") == "stated"
    assert prose(b"was approximately $5.2 million.") == "stated"
    note = b"""<p>(in millions)</p><table>
<tr><td></td><td colspan="3">Three Months Ended June 30, 2025</td></tr>
<tr><td></td><td>Note</td><td>Current</td><td>Prior</td></tr>
<tr><td>Net income</td><td>5</td><td>4.0</td><td>3.0</td></tr></table>"""
    assert classify(note, record=dict(RECORD, current_ni="5000000"))["current_ni"] == "label_only"
    assert classify(note, record=dict(RECORD, current_ni="4000000"))["current_ni"] == "stated"


def test_document_currency_declarations_and_forecast_headings_reach_later_blocks():
    declared = b"<p>All amounts are in Canadian dollars.</p><p>One.</p><p>Two.</p><p>Three.</p>"
    cad = table([b"Three Months Ended June 30, 2025"], [b"Net income", b"$5.2"])
    assert classify(declared + cad)["current_ni"] == "currency_mismatch"
    assert classify(cad)["current_ni"] == "stated"
    prose = b"<p>Net income for Q2 FY2025 was %s million.</p>"
    assert classify(declared + prose % b"$5.2")["current_ni"] == "currency_mismatch"
    assert classify(declared + prose % b"US$5.2")["current_ni"] == "stated"
    result = prose % b"$5.2"
    assert classify(b"<h2>Outlook</h2>" + result)["current_ni"] == "label_only"
    assert classify(b"<h2>Second Quarter Results</h2>" + result)["current_ni"] == "stated"
    later = b"<h2>Outlook</h2><p>We expect growth.</p><h2>Results</h2>" + result
    assert classify(later)["current_ni"] == "stated"  # a new heading ends the outlook section
    bullet = b"<li>Raising full-year outlook</li><li>Net income for Q2 FY2025 was $5.2 million</li>"
    assert classify(bullet)["current_ni"] == "stated"  # a sentence-case bullet is not a heading


# ------------------------------------------------------------------ documents and identity


def test_release_identification():
    def doc(t, desc, text=""):
        return {"type": t, "description": desc, "url": t, "parsed": {"text": text}}

    pair = [doc("EX-99.1", "Press Release"), doc("EX-99.2", "Slides")]
    assert m.identify_release(pair)[0] == "release"
    assert m.identify_release([doc("EX-99.1", "", "ACME earnings release")])[0] == "release"
    assert m.identify_release([doc("EX-99.1", ""), doc("EX-99.2", "")])[0] == "release_by_type"
    two = [doc("EX-99.1", "Press release"), doc("EX-99.2", "News release")]
    assert m.identify_release(two)[0] == "release_ambiguous"
    assert m.identify_release([doc("EX-99.2", ""), doc("EX-99.3", "")])[0] == "release_unidentified"
    hyphen = [doc("EX-99.1", "Investor slides"), doc("EX-99.2", "Press-Release")]
    assert m.identify_release(hyphen) == ("release", [hyphen[1]])
    dash = [doc("EX-99.1", "Slides"), doc("EX-99.2", "", "ACME Earnings—Release")]
    assert m.identify_release(dash) == ("release", [dash[1]])


def test_document_kinds():
    assert m.document_kind("x.pdf", b"%PDF-1.4") == "unsupported"
    assert m.document_kind("x.htm", b"<html>") == "html"
    assert m.document_kind("x.txt", b"text") == "text"
    assert m.document_kind("x.jpg", b"\xff\xd8") == "unsupported"


def header(
    cik="0000000001",
    form="8-K",
    items=("2.02", "9.01"),
    acc="0001104659-24-000001",
    accepted="20240725161500",
):
    lines = [f"<ACCEPTANCE-DATETIME>{accepted}", f"<ACCESSION-NUMBER>{acc}", f"<TYPE>{form}"]
    lines += [f"<ITEMS>{i}" for i in items] + ["<FILING-DATE>20240725"]
    lines += ["<FILER>", "<COMPANY-DATA>", f"<CIK>{cik}", "</COMPANY-DATA>", "</FILER>"]
    return "\n".join(lines)


def test_header_identity():
    def issues(text):
        return m.header_identity(text, "0000000001", "0001104659-24-000001")["issues"]

    m.Frozen(REPO)  # locks tzdata before any zone is resolved
    good = m.header_identity(header(), "0000000001", "0001104659-24-000001")
    assert good["issues"] == [] and good["acceptance"] == "2024-07-25T16:15:00-04:00"
    assert issues(header(cik="0000000009")) and issues(header(form="10-Q"))
    assert issues(header(items=("8.01",))) and issues(header(acc="0001104659-24-000002"))
    missing = m.header_identity(header(accepted="2024", cik=""), "0000000001", "x")
    assert missing["missing"] == ["header CIK missing", "header acceptance or filing date missing"]
    assert missing["issues"] == ["header accession mismatch"]
    subject = (
        "<SUBJECT-COMPANY>\n<COMPANY-DATA>\n<CIK>0000000001\n</COMPANY-DATA>\n</SUBJECT-COMPANY>"
    )
    other = header(cik="0000000009") + "\n" + subject
    assert "header CIK mismatch" in issues(other)  # the issuer only as subject company
    alone = header().split("<FILER>")[0] + subject
    only = m.header_identity(alone, "0000000001", "0001104659-24-000001")
    assert "header CIK missing" in only["missing"] and only["ciks"] == []
    unclosed = header(cik="0000000009").replace("</FILER>", "") + "\n" + subject
    assert "header CIK mismatch" in issues(unclosed)  # an open filer block ends at the subject


def test_archive_url_uses_issuer_cik_for_agent_filings():
    frozen = m.Frozen(REPO)
    base = frozen.capture.archive_base({"cik": "0000000001"}, "0001104659-24-000001")
    assert base == "https://www.sec.gov/Archives/edgar/data/1/000110465924000001/"


def test_projection_never_decodes_unapproved_fields(tmp_path):
    frozen = m.Frozen(REPO)
    path = tmp_path / "records.json"
    huge = "7" * 5000  # json.loads cannot decode this integer
    path.write_text(
        '[{"accession": "a", "status": "qualified", "all_facts": ' + huge + "},"
        ' {"accession": "b", "status": "x"}]',
        encoding="utf-8",
    )
    assert m.project_values(frozen, path, ["a"]) == {"a": {"accession": "a", "status": "qualified"}}


# ------------------------------------------------------------------ statistics


def test_signals_bounds_and_verdicts():
    def event(classes, kind="release", status="examined"):
        comps = {n: {"classification": classes.get(n, "stated")} for n in m.COMPONENTS}
        e = {"components": comps, "release": {"kind": kind}, "event_status": status}
        return e

    assert m.signal(event({}), m.S_FLOW) == {"comparable": True, "lower": True, "upper": True}
    unverified = m.signal(event({"current_ni": "period_unverified"}), m.S_FLOW)
    assert unverified["lower"] is False and unverified["upper"] is True
    assert m.signal(event({"current_ni": "identity_failed"}), m.S_FLOW)["upper"] is False
    ambiguous = m.signal(event({}, kind="release_ambiguous"), m.S_FLOW)
    assert ambiguous == {"comparable": True, "lower": False, "upper": True}
    empty = m.signal(event({"current_ni": "not_found"}, kind="release_ambiguous"), m.S_FLOW)
    assert empty["upper"] is False
    assert m.signal(event({"current_ni": "currency_mismatch"}), m.S_FLOW)["upper"] is False
    assert m.signal(event({"current_ni": "scale_unverified"}), m.S_FLOW)["upper"] is True
    unverified = dict(event({}), identity_unverified=True)
    assert m.signal(unverified, m.S_FLOW) == {"comparable": True, "lower": False, "upper": True}
    assert m.signal(event({"q_prior_ni": "not_comparable"}), m.Q_FLOW)["comparable"] is False
    rules = DEFINITION["interpretation"]["thresholds"]
    assert m.verdict(150, 150, 150, rules)[0] == "release_complete_common"
    assert m.verdict(0, 10, 150, rules)[0] == "release_complete_rare"
    assert m.verdict(80, 120, 150, rules)[0] == "inconclusive"
    low, high = m.wilson(75, 150)
    assert 0.41 < low < 0.43 and 0.57 < high < 0.59


# ------------------------------------------------------------------ end-to-end lifecycle


def calendar():
    sessions, d = [], date(2024, 1, 2)
    while d <= date(2025, 12, 31):
        if d.weekday() < 5:
            s = d.isoformat()
            sessions.append(
                {"session": s, "open": s + "T13:30:00+00:00", "close": s + "T20:00:00+00:00"}
            )
        d += timedelta(days=1)
    return sessions


ISSUERS = [("AAA", "0000000001"), ("BBB", "0000000002"), ("CCC", "0000000003")]


def ids(i):
    cik = ISSUERS[i][1]
    return cik, f"{cik}-24-000010", f"0001104659-24-00000{i + 1}"


def site(release=None, pdf_for=2, wrong_cik_for=1):
    """URL -> bytes for every sampled filing."""
    pages = {}
    for i, (symbol, cik) in enumerate(ISSUERS):
        _, _, k = ids(i)
        base = f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{k.replace('-', '')}/"
        name = "ex991.pdf" if i == pdf_for else "ex991.htm"
        rows = [("FORM 8-K", "d8k.htm", "8-K"), ("PRESS RELEASE", name, "EX-99.1")]
        rows += [("XBRL", "x.xml", "EX-101.INS")]
        table = "".join(
            f'<tr><td>{n}</td><td>{d}</td><td><a href="{base}{f}">{f}</a></td><td>{t}</td></tr>'
            for n, (d, f, t) in enumerate(rows, 1)
        )
        pages[base + k + "-index.html"] = (
            f"<html><body><div>SEC Accession No. {k}</div><table>{table}</table></body></html>"
        ).encode()
        filer = "0000000099" if i == wrong_cik_for else cik
        pages[base + k + ".hdr.sgml"] = header(cik=filer, acc=k).encode()
        pages[base + name] = b"%PDF-1.4 binary" if i == pdf_for else (release or release_html())
    return pages


class Response(io.BytesIO):
    def __init__(self, url, data, status=200):
        super().__init__(data)
        self.url, self.status, self.headers = url, status, {"Content-Type": "text/html"}


class Cut(io.BytesIO):
    """A response whose body ends before its declared length."""

    def __init__(self, url):
        super().__init__(b"")
        self.url, self.status, self.headers = url, 200, {"Content-Type": "text/html"}

    def read(self, *args):
        raise http.client.IncompleteRead(b"part", 100)


class Opener:
    def __init__(self, pages, fail=None):
        self.pages, self.fail, self.calls = pages, dict(fail or {}), []

    def open(self, request, timeout):
        url = request.full_url
        self.calls.append(url)
        action = self.fail.pop(url, None)
        if action == "interrupt":
            raise KeyboardInterrupt
        if action == "incomplete":
            return Cut(url)
        if action == "transport":
            raise URLError("network down")
        if isinstance(action, int):
            raise HTTPError(url, action, "error", {}, io.BytesIO(b""))
        if url not in self.pages:
            raise HTTPError(url, 404, "missing", {}, io.BytesIO(b""))
        return Response(url, self.pages[url])


def build(tmp, records=None, requests=None):
    repo, study = tmp / "repo", tmp / "repo" / ".qualification" / m.STUDY
    study.mkdir(parents=True)
    for relative in (m.AUDIT[0], m.CAPTURE[0], m.FEATURES[0]):
        (repo / relative).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(REPO / relative, repo / relative)
    shutil.copy(HERE / "probe.py", study / "probe.py")
    frozen = m.Frozen(repo)
    cal = calendar()
    events = []
    for i, (symbol, cik) in enumerate(ISSUERS):
        _, q, k = ids(i)
        session = frozen.session("2025-08-05T20:00:00.000Z", "2025-08-05", cal)
        events.append(
            {
                "accession": q,
                "symbol": symbol,
                "cik": cik,
                "filing_date": "2025-08-05",
                "acceptance": "2025-08-05T20:00:00.000Z",
                "q_entry_session": session,
                "strategy_source_qualified": True,
                "status": "single_prior",
                "candidates": [{"accession": k}],
            }
        )
    events.append(dict(events[0], accession="0000000001-24-000099", status="multiple"))
    paths = DEFINITION["paths"]
    records = (
        records
        if records is not None
        else [dict(RECORD, accession=ids(i)[1], all_facts=[1, 2, 3]) for i in range(3)]
    )
    files = {
        paths["timing_events"]: json.dumps(events).encode(),
        paths["calendar"]: json.dumps(cal).encode(),
        paths["records"]: json.dumps(records).encode(),
        "pyproject.toml": b"[project]\n",
        "uv.lock": b"version = 1\n",
    }
    for relative, data in files.items():
        (repo / relative).parent.mkdir(parents=True, exist_ok=True)
        (repo / relative).write_bytes(data)
    (repo / paths["shared_source_lock"]).write_bytes(b"")
    definition = json.loads(json.dumps(DEFINITION))
    definition["inputs"] = {r: sha(d) for r, d in files.items()}
    definition["population"]["size"] = 3
    definition["sample"]["size"] = 3
    definition["requests"]["minimum_request_interval_seconds"] = 0
    definition["requests"].update(requests or {})
    raw = (json.dumps(definition, indent=1) + "\n").encode()
    (study / "definition.json").write_bytes(raw)
    code = {r: sha((repo / r).read_bytes()) for r in (m.AUDIT[0], m.CAPTURE[0], m.FEATURES[0])}
    code[f".qualification/{m.STUDY}/probe.py"] = sha((study / "probe.py").read_bytes())
    (study / "freeze.json").write_text(json.dumps({"definition_sha256": sha(raw), "code": code}))
    return repo, study


def go(repo, study, opener, **kwargs):
    return m.run(study / "definition.json", study / "freeze.json", repo, study, opener, **kwargs)


REAL_PROCESSES = m.processes


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def refuse(*args, **kwargs):
        raise AssertionError("network access attempted")

    monkeypatch.setattr(socket, "socket", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)
    # Hermetic by default: only this process runs; one test below lists real processes.
    monkeypatch.setattr(m, "processes", lambda: [(os.getpid(), 0, "pytest")])


def test_other_research_workers_block_before_any_request(tmp_path, monkeypatch):
    repo, study = build(tmp_path)
    worker = (424242, 1, "python .qualification/filing-source20260928/capture.py --run")
    editor = (434343, 1, "code .qualification/exhibit-content20261002/probe.py")
    monkeypatch.setattr(m, "processes", lambda: [(os.getpid(), 0, "pytest"), worker, editor])
    opener = Opener(site())
    with pytest.raises(m.ProbeError, match="Other research workers"):
        go(repo, study, opener)
    assert opener.calls == [] and not (study / "attempts").exists()
    ready = m.preflight(study / "definition.json", study / "freeze.json", repo, study)
    assert not ready["ready"]
    assert [b["problem"] for b in ready["blocking"]] == [[{"pid": 424242, "command": worker[2]}]]


def test_workers_started_without_a_qualified_path_are_seen(tmp_path, monkeypatch):
    repo, study = build(tmp_path)
    for command in (
        "py capture.py --run",
        "C:\\Python313\\pythonw.exe audit.py",
        "uv run probe.py",
    ):
        rows = [(os.getpid(), 0, "pytest"), (424242, 1, command)]
        monkeypatch.setattr(m, "processes", lambda rows=rows: rows)
        assert [w["pid"] for w in m.other_workers(repo)] == [424242], command
    for command in ("code capture.py", "python -m http.server", "python other_tool.py"):
        rows = [(os.getpid(), 0, "pytest"), (424242, 1, command)]
        monkeypatch.setattr(m, "processes", lambda rows=rows: rows)
        assert m.other_workers(repo) == [], command


def test_process_listing_excludes_this_process_and_its_ancestors(monkeypatch):
    monkeypatch.setattr(m, "processes", REAL_PROCESSES)
    rows = m.processes()
    assert os.getpid() in {pid for pid, _, _ in rows}
    assert os.getpid() not in {w["pid"] for w in m.other_workers()}


def test_end_to_end_run_and_reanalysis(tmp_path):
    repo, study = build(tmp_path)
    ready = m.preflight(study / "definition.json", study / "freeze.json", repo, study)
    assert ready["ready"] and ready["sample_size"] == 3
    opener = Opener(site())
    attempt = go(repo, study, opener)
    meta = json.loads((attempt / "attempt.json").read_text())
    assert meta["status"] == "complete"
    rows = {r["symbol"]: r for r in json.loads((attempt / "events.json").read_text())}
    assert all(c["classification"] == "stated" for c in rows["AAA"]["components"].values())
    assert rows["AAA"]["signals"]["S_flow"] == {"comparable": True, "lower": True, "upper": True}
    assert rows["BBB"]["event_status"] == "identity_failed"
    assert rows["CCC"]["components"]["current_ni"]["classification"] == "exhibit_unavailable"
    summary = json.loads((attempt / "summary.json").read_text())["all"]["signals"]["S_flow"]
    assert (summary["lower_count"], summary["upper_count"], summary["comparable"]) == (1, 2, 3)
    assert len(opener.calls) == 9 and "data.sec.gov" not in " ".join(opener.calls)
    projection = json.loads((attempt / "projection.json").read_text())
    assert "all_facts" not in json.dumps(projection)
    check = m.reanalyze(attempt.name, study / "definition.json", study / "freeze.json", repo, study)
    assert check["events_identical"] and check["summary_identical"]
    with pytest.raises(m.ProbeError, match="already exists"):
        go(repo, study, Opener(site()))
    with pytest.raises(m.ProbeError, match="only running or halted"):
        go(repo, study, Opener(site()), resume=attempt.name)
    assert not m.preflight(study / "definition.json", study / "freeze.json", repo, study)["ready"]
    stated = rows["AAA"]["components"]["current_ni"]["evidence"]
    assert stated and all(len(e["sha256"]) == 64 for e in stated)
    component = json.loads((attempt / "summary.json").read_text())["all"]["components"]
    assert (
        component["current_ni"]["comparable"] == 3 and component["current_ni"]["lower_count"] == 1
    )
    assert component["current_ni"]["classifications"]["identity_failed"] == 1
    spot = json.loads((attempt / "spot-check.json").read_text())
    assert sorted(r["accession"] for r in spot) == sorted(rows[s]["accession"] for s in rows)


def test_header_reclocked_to_the_10q_session_is_not_prior(tmp_path):
    repo, study = build(tmp_path)
    pages = site(wrong_cik_for=None, pdf_for=None)
    for url in [u for u in pages if u.endswith(".hdr.sgml")]:
        pages[url] = pages[url].replace(b"20240725161500", b"20250805180000")
    attempt = go(repo, study, Opener(pages))
    rows = json.loads((attempt / "events.json").read_text())
    assert {r["event_status"] for r in rows} == {"header_not_prior"}


def test_missing_header_identity_is_unverified_not_failed(tmp_path):
    repo, study = build(tmp_path)
    pages = site(wrong_cik_for=None, pdf_for=None)
    for url in [u for u in pages if u.endswith(".hdr.sgml")]:
        pages[url] = pages[url].replace(b"<CIK>", b"<NOTE>")
    attempt = go(repo, study, Opener(pages))
    rows = json.loads((attempt / "events.json").read_text())
    assert {r["event_status"] for r in rows} == {"examined"}
    assert all(r["identity_unverified"] for r in rows)
    assert {(r["signals"]["S_flow"]["lower"], r["signals"]["S_flow"]["upper"]) for r in rows} == {
        (False, True)
    }
    summary = json.loads((attempt / "summary.json").read_text())["all"]
    assert summary["flags"]["identity_unverified"] == 3


def test_overflowing_index_fetches_no_exhibit(tmp_path):
    repo, study = build(tmp_path)
    pages = site(wrong_cik_for=None, pdf_for=None)
    index = next(u for u in pages if u.endswith("-index.html"))
    base = index.rsplit("/", 1)[0] + "/"
    extra = "".join(
        f'<tr><td>9</td><td>Exhibit</td><td><a href="{base}e{i}.htm">e{i}.htm</a></td>'
        f"<td>EX-99.{i + 2}</td></tr>"
        for i in range(10)
    )
    pages[index] = pages[index].replace(b"</table>", extra.encode() + b"</table>")
    opener = Opener(pages)
    attempt = go(repo, study, opener)
    assert not [u for u in opener.calls if u.startswith(base) and u.endswith(".htm")]
    rows = {r["symbol"]: r for r in json.loads((attempt / "events.json").read_text())}
    assert rows["AAA"]["reason"] == "exhibit_overflow"


def test_crash_before_the_attempt_record_leaves_no_attempt(tmp_path, monkeypatch):
    repo, study = build(tmp_path)
    original = m.write_json

    def crash(frozen, path, value):
        if Path(path).parent.name.endswith(".init"):
            raise KeyboardInterrupt
        return original(frozen, path, value)

    with monkeypatch.context() as patch:
        patch.setattr(m, "write_json", crash)
        with pytest.raises(KeyboardInterrupt):
            go(repo, study, Opener(site()))
    assert m.attempts(study) == []
    ready = m.preflight(study / "definition.json", study / "freeze.json", repo, study)
    assert ready["ready"] and len(ready["uninitialised_staging"]) == 1
    opener = Opener(site())
    attempt = go(repo, study, opener)
    assert json.loads((attempt / "attempt.json").read_text())["status"] == "complete"


def test_interruption_before_projection_is_completed_on_resume(tmp_path, monkeypatch):
    repo, study = build(tmp_path)

    write_json = m.write_json

    def stop(frozen, path, value):  # interrupted while the projection is written
        if Path(path).name == "projection.json":
            raise KeyboardInterrupt
        return write_json(frozen, path, value)

    with monkeypatch.context() as patch:
        patch.setattr(m, "write_json", stop)
        with pytest.raises(KeyboardInterrupt):
            go(repo, study, Opener(site()))
    attempt = next((study / "attempts").iterdir())
    assert (attempt / "sample.json").exists() and not (attempt / "projection.json").exists()
    with pytest.raises(m.ProbeError, match="complete attempt"):
        m.reanalyze(attempt.name, study / "definition.json", study / "freeze.json", repo, study)
    go(repo, study, Opener(site()), resume=attempt.name)
    assert json.loads((attempt / "attempt.json").read_text())["status"] == "complete"


def test_rate_limit_halts_and_resumes_only_with_acknowledgement(tmp_path):
    repo, study = build(tmp_path)
    url = next(u for u in site() if u.endswith("ex991.pdf"))
    with pytest.raises(m.ProbeError, match="Halted"):
        go(repo, study, Opener(site(), fail={url: 429}))
    attempt = next((study / "attempts").iterdir())
    assert json.loads((attempt / "attempt.json").read_text())["status"] == "halted"
    assert (attempt / "source" / "STOP.json").exists()
    with pytest.raises(m.ProbeError, match="acknowledge"):
        go(repo, study, Opener(site()), resume=attempt.name)
    opener = Opener(site())
    go(repo, study, opener, resume=attempt.name, acknowledge_stop=True)
    assert url not in opener.calls  # a saved outcome is never requested again
    rows = {r["symbol"]: r for r in json.loads((attempt / "events.json").read_text())}
    assert rows["CCC"]["components"]["current_ni"]["classification"] == "exhibit_unavailable"
    assert list((attempt / "source").glob("STOP-acknowledged-*.json"))


def test_unidentified_release_still_reports_any_ex99(tmp_path):
    repo, study = build(tmp_path)
    pages = site(wrong_cik_for=None, pdf_for=None)
    for url in [u for u in pages if u.endswith("-index.html")]:
        pages[url] = (
            pages[url].replace(b"PRESS RELEASE", b"EXHIBIT").replace(b"EX-99.1", b"EX-99.2")
        )
    attempt = go(repo, study, Opener(pages))
    rows = json.loads((attempt / "events.json").read_text())
    assert {r["reason"] for r in rows} == {"release_unidentified"}
    assert all(r["any_ex99"]["current_ni"] == "stated" for r in rows)
    summary = json.loads((attempt / "summary.json").read_text())["all"]
    assert summary["stated_in_any_ex99"]["current_ni"] == 3


def test_any_ex99_readout_needs_a_verified_identity(tmp_path):
    repo, study = build(tmp_path)
    pages = site(wrong_cik_for=None, pdf_for=None)
    for url in [u for u in pages if u.endswith("-index.html")]:
        pages[url] = (
            pages[url].replace(b"PRESS RELEASE", b"EXHIBIT").replace(b"EX-99.1", b"EX-99.2")
        )
    first = next(u for u in pages if u.endswith(".hdr.sgml"))
    pages[first] = pages[first].replace(b"<TYPE>8-K", b"")  # the form is missing: unverified
    attempt = go(repo, study, Opener(pages))
    rows = {r["symbol"]: r for r in json.loads((attempt / "events.json").read_text())}
    assert rows["AAA"]["identity_unverified"] and rows["AAA"]["any_ex99"] == {}
    summary = json.loads((attempt / "summary.json").read_text())["all"]
    assert summary["stated_in_any_ex99"]["current_ni"] == 2


def test_saved_error_responses_are_verified(tmp_path):
    frozen = m.Frozen(REPO)
    url = "https://www.sec.gov/Archives/edgar/data/1/000110465924000001/ex992.htm"
    body = b"<html>Not Found</html>"
    (tmp_path / "raw").mkdir()
    (tmp_path / "resources").mkdir()
    (tmp_path / "raw" / (sha(body) + ".bin")).write_bytes(body)
    meta = {"url": url, "status": 404, "error": "HTTP 404", "bytes": len(body)}
    meta.update(sha256=sha(body), path="raw/" + sha(body) + ".bin")
    record = tmp_path / "resources" / (frozen.capture.sha(url.encode()) + ".json")
    record.write_text(json.dumps(meta))
    assert m.saved(tmp_path, frozen.capture, url) == (None, "HTTP 404")
    (tmp_path / "raw" / (sha(body) + ".bin")).write_bytes(body + b" ")
    with pytest.raises(m.ProbeError, match="Saved response changed"):
        m.saved(tmp_path, frozen.capture, url)


def test_transport_failure_stop_survives_a_crash_before_stop_json(tmp_path):
    repo, study = build(tmp_path)
    first = next(iter(site()))
    with pytest.raises(m.ProbeError, match="Transport failure"):
        go(repo, study, Opener(site(), fail={first: "transport"}))
    attempt = next((study / "attempts").iterdir())
    (attempt / "source" / "STOP.json").unlink()  # as if the crash came before it was written
    with pytest.raises(m.ProbeError, match="Transport failure"):
        go(repo, study, Opener(site()), resume=attempt.name)
    go(repo, study, Opener(site()), resume=attempt.name, acknowledge_stop=True)
    assert json.loads((attempt / "attempt.json").read_text())["status"] == "complete"


def test_reanalysis_checks_the_recorded_output_bytes(tmp_path):
    repo, study = build(tmp_path)
    attempt = go(repo, study, Opener(site()))
    args = (attempt.name, study / "definition.json", study / "freeze.json", repo, study)
    check = m.reanalyze(*args)
    assert check["reproduced"] and check["spot_check_identical"] and check["files_match_record"]
    events = attempt / "events.json"
    events.write_text(json.dumps(json.loads(events.read_text()), indent=2), encoding="utf-8")
    check = m.reanalyze(*args)
    assert check["events_identical"] and not check["files_match_record"]
    assert not check["reproduced"]


def test_reanalysis_checks_the_saved_source_records(tmp_path):
    repo, study = build(tmp_path)
    attempt = go(repo, study, Opener(site()))
    args = (attempt.name, study / "definition.json", study / "freeze.json", repo, study)
    meta = json.loads((attempt / "attempt.json").read_text())
    assert "requests.jsonl" in meta["source"] and any(k.startswith("raw/") for k in meta["source"])
    assert m.reanalyze(*args)["source_matches_record"]
    journal = attempt / "source" / "requests.jsonl"
    saved = journal.read_bytes()
    journal.write_bytes(saved.replace(b'"at": "', b'"at":  "', 1))
    check = m.reanalyze(*args)
    assert check["events_identical"] and not check["source_matches_record"]
    assert not check["reproduced"]
    journal.write_bytes(saved)
    record = next((attempt / "source" / "resources").glob("*.json"))
    record.write_bytes(record.read_bytes().replace(b"retrieved_at_utc", b"retrieved_at_UTC"))
    assert not m.reanalyze(*args)["reproduced"]


def test_a_raw_payload_left_without_its_record_is_bound_to_the_attempt(tmp_path):
    repo, study = build(tmp_path)
    first = next(iter(site()))
    with pytest.raises(KeyboardInterrupt):
        go(repo, study, Opener(site(), fail={first: "interrupt"}))
    attempt = next((study / "attempts").iterdir())
    orphan_bytes = b"<html>a complete first response whose record was never written</html>"
    orphan = attempt / "source" / "raw" / (sha(orphan_bytes) + ".bin")
    orphan.write_bytes(orphan_bytes)  # a crash after the raw write, before the record
    go(repo, study, Opener(site()), resume=attempt.name)
    meta = json.loads((attempt / "attempt.json").read_text())
    assert meta["source"]["raw/" + orphan.name] == sha(orphan_bytes)
    args = (attempt.name, study / "definition.json", study / "freeze.json", repo, study)
    assert m.reanalyze(*args)["reproduced"]
    orphan.unlink()
    check = m.reanalyze(*args)
    assert check["events_identical"] and not check["source_matches_record"]


def test_reanalysis_checks_the_active_runtime(tmp_path, monkeypatch):
    repo, study = build(tmp_path)
    attempt = go(repo, study, Opener(site()))
    args = (attempt.name, study / "definition.json", study / "freeze.json", repo, study)
    assert m.reanalyze(*args)["runtime_matches_record"]
    record = attempt / "attempt.json"
    meta = json.loads(record.read_text())
    meta["runtime"]["new_york_tzif_sha256"] = "0" * 64  # began under other zone data
    record.write_text(json.dumps(meta), encoding="utf-8")
    check = m.reanalyze(*args)
    assert check["events_identical"] and not check["runtime_matches_record"]
    assert not check["reproduced"]
    real = m.runtime_problems
    monkeypatch.setattr(m, "runtime_problems", lambda f, d: (real(f, d)[0], ["Python 3.12.0"]))
    with pytest.raises(m.ProbeError, match="Python 3.12.0"):
        m.reanalyze(*args)


def test_reanalysis_rechecks_inputs_and_projection(tmp_path):
    repo, study = build(tmp_path)
    attempt = go(repo, study, Opener(site()))
    args = (attempt.name, study / "definition.json", study / "freeze.json", repo, study)
    assert m.reanalyze(*args)["events_identical"]
    projection = attempt / "projection.json"
    saved = projection.read_bytes()
    projection.write_bytes(saved.replace(b"5200000", b"5200001"))
    with pytest.raises(m.ProbeError, match="Saved projection"):
        m.reanalyze(*args)
    projection.write_bytes(saved)
    calendar = repo / DEFINITION["paths"]["calendar"]
    saved = calendar.read_bytes()
    calendar.write_bytes(saved + b" ")
    with pytest.raises(m.ProbeError, match="Input missing or changed"):
        m.reanalyze(*args)
    calendar.write_bytes(saved)
    lock = repo / "uv.lock"
    lock.write_bytes(lock.read_bytes() + b"# changed\n")  # a dependency identity changed
    with pytest.raises(m.ProbeError, match="Input missing or changed: uv.lock"):
        m.reanalyze(*args)


def test_a_url_interrupted_at_its_ceiling_becomes_a_reviewed_failure(tmp_path):
    repo, study = build(tmp_path)
    first = next(iter(site()))
    with pytest.raises(KeyboardInterrupt):
        go(repo, study, Opener(site(), fail={first: "interrupt"}))
    attempt = next((study / "attempts").iterdir())
    with pytest.raises(KeyboardInterrupt):
        go(repo, study, Opener(site(), fail={first: "interrupt"}), resume=attempt.name)
    opener = Opener(site())
    with pytest.raises(m.ProbeError, match="(?i)attempt ceiling"):
        go(repo, study, opener, resume=attempt.name)
    assert first not in opener.calls and (attempt / "source" / "STOP.json").exists()
    go(repo, study, Opener(site()), resume=attempt.name, acknowledge_stop=True)
    rows = {r["symbol"]: r for r in json.loads((attempt / "events.json").read_text())}
    assert rows["AAA"]["event_status"] == "exhibit_unavailable"


def test_lifetime_ceiling_stops_once_then_fails_remaining_urls(tmp_path):
    repo, study = build(tmp_path, requests={"max_lifetime_network_attempts": 4})
    pages = site(wrong_cik_for=None, pdf_for=None)
    with pytest.raises(m.ProbeError, match="(?i)attempt ceiling"):
        go(repo, study, Opener(pages))
    attempt = next((study / "attempts").iterdir())
    go(repo, study, Opener(pages), resume=attempt.name, acknowledge_stop=True)
    statuses = sorted(r["event_status"] for r in json.loads((attempt / "events.json").read_text()))
    assert statuses == ["examined", "exhibit_unavailable", "exhibit_unavailable"]
    assert json.loads((attempt / "attempt.json").read_text())["status"] == "complete"
    assert len(list((attempt / "source").glob("STOP-acknowledged-*.json"))) == 1


def test_partial_raw_file_is_quarantined_before_the_cache_opens(tmp_path):
    repo, study = build(tmp_path)
    url = next(u for u in site() if u.endswith("ex991.pdf"))
    with pytest.raises(m.ProbeError, match="Halted"):
        go(repo, study, Opener(site(), fail={url: 429}))
    attempt = next((study / "attempts").iterdir())
    full = site(wrong_cik_for=None)[next(u for u in site() if u.endswith("-index.html"))]
    partial = attempt / "source" / "raw" / (sha(full + b"x") + ".bin")
    partial.write_bytes(full[:10])  # as if a crash cut a direct raw write short
    go(repo, study, Opener(site()), resume=attempt.name, acknowledge_stop=True)
    meta = json.loads((attempt / "attempt.json").read_text())
    assert meta["status"] == "complete" and not partial.exists()
    assert meta["quarantined_partial_raw"][0]["files"] == [partial.name]


def test_a_record_whose_payload_was_cut_short_is_quarantined_and_retried(tmp_path):
    repo, study = build(tmp_path)
    url = next(u for u in site() if u.endswith("ex991.pdf"))
    with pytest.raises(m.ProbeError, match="Halted"):
        go(repo, study, Opener(site(), fail={url: 429}))
    attempt = next((study / "attempts").iterdir())
    saved = [json.loads(r.read_text()) for r in (attempt / "source" / "resources").iterdir()]
    first = next(r for r in saved if r.get("status") == 200)
    record = attempt / "source" / "resources" / (sha(first["url"].encode()) + ".json")
    raw = attempt / "source" / first["path"]
    raw.write_bytes(raw.read_bytes()[:10])  # the record was durable, the raw write was not
    opener = Opener(site())
    go(repo, study, opener, resume=attempt.name, acknowledge_stop=True)
    meta = json.loads((attempt / "attempt.json").read_text())
    assert meta["status"] == "complete" and first["url"] in opener.calls  # its second attempt
    assert meta["quarantined_partial_raw"][0]["files"] == [raw.name, "resources/" + record.name]
    assert len(list((attempt / "source" / "partial").glob(record.name + ".*"))) == 1


def test_an_incomplete_read_halts_for_review_and_keeps_its_retry(tmp_path):
    repo, study = build(tmp_path)
    url = next(u for u in site() if u.endswith("ex991.pdf"))
    with pytest.raises(m.ProbeError, match="Transport failure"):
        go(repo, study, Opener(site(), fail={url: "incomplete"}))
    attempt = next((study / "attempts").iterdir())
    assert json.loads((attempt / "attempt.json").read_text())["status"] == "halted"
    stop = json.loads((attempt / "source" / "STOP.json").read_text())
    assert stop["url"] == url and stop["error"].startswith("IncompleteRead")
    opener = Opener(site())
    go(repo, study, opener, resume=attempt.name, acknowledge_stop=True)
    assert url in opener.calls  # its second attempt
    assert json.loads((attempt / "attempt.json").read_text())["status"] == "complete"


def test_a_saved_access_stop_is_restored_after_a_crash_before_stop_json(tmp_path):
    repo, study = build(tmp_path)
    url = next(u for u in site() if u.endswith("ex991.pdf"))
    with pytest.raises(m.ProbeError, match="Halted"):
        go(repo, study, Opener(site(), fail={url: 429}))
    attempt = next((study / "attempts").iterdir())
    (attempt / "source" / "STOP.json").unlink()  # killed after the 429 record, before STOP.json
    opener = Opener(site())
    with pytest.raises(m.ProbeError, match="access or size stop"):
        go(repo, study, opener, resume=attempt.name)
    assert opener.calls == [] and (attempt / "source" / "STOP.json").exists()
    go(repo, study, Opener(site()), resume=attempt.name, acknowledge_stop=True)
    assert json.loads((attempt / "attempt.json").read_text())["status"] == "complete"


def test_resume_refuses_a_journal_edited_since_its_checkpoint(tmp_path):
    repo, study = build(tmp_path)
    first = next(iter(site()))
    with pytest.raises(KeyboardInterrupt):
        go(repo, study, Opener(site(), fail={first: "interrupt"}))
    attempt = next((study / "attempts").iterdir())
    mark = json.loads((attempt / "attempt.json").read_text())["journal"]
    journal = attempt / "source" / "requests.jsonl"
    saved = journal.read_bytes()
    assert mark["bytes"] == len(saved) > 0 and mark["sha256"] == sha(saved)
    journal.write_bytes(b"")  # a deleted request_started line would reset the URL's count
    opener = Opener(site())
    with pytest.raises(m.ProbeError, match="journal differs"):
        go(repo, study, opener, resume=attempt.name)
    assert opener.calls == []
    journal.write_bytes(saved)
    go(repo, study, Opener(site()), resume=attempt.name)
    assert json.loads((attempt / "attempt.json").read_text())["status"] == "complete"


def test_each_request_start_is_bound_before_the_request_is_sent(tmp_path):
    repo, study = build(tmp_path)
    bound = []

    class Watching(Opener):
        def open(self, request, timeout):
            attempt = next((study / "attempts").iterdir())
            mark = json.loads((attempt / "attempt.json").read_text())["journal"]
            journal = (attempt / "source" / "requests.jsonl").read_bytes()
            last = json.loads(journal.splitlines()[-1])
            bound.append(
                mark == {"bytes": len(journal), "sha256": sha(journal)}
                and last["event"] == "request_started"
                and last["url"] == request.full_url
            )
            return super().open(request, timeout)

    go(repo, study, Watching(site()))
    assert len(bound) == 9 and all(bound)  # a hard crash mid-request leaves the start bound


def test_a_refused_resume_keeps_the_stop_and_the_halted_state(tmp_path):
    repo, study = build(tmp_path)
    url = next(u for u in site() if u.endswith("ex991.pdf"))
    with pytest.raises(m.ProbeError, match="Halted"):
        go(repo, study, Opener(site(), fail={url: 429}))
    attempt = next((study / "attempts").iterdir())
    journal = attempt / "source" / "requests.jsonl"
    saved = journal.read_bytes()
    journal.write_bytes(b"")
    with pytest.raises(m.ProbeError, match="journal differs"):
        go(repo, study, Opener(site()), resume=attempt.name, acknowledge_stop=True)
    assert (attempt / "source" / "STOP.json").exists()
    assert not list((attempt / "source").glob("STOP-acknowledged-*.json"))
    assert json.loads((attempt / "attempt.json").read_text())["status"] == "halted"
    journal.write_bytes(saved)
    go(repo, study, Opener(site()), resume=attempt.name, acknowledge_stop=True)
    assert json.loads((attempt / "attempt.json").read_text())["status"] == "complete"


def test_incomplete_journal_tail_is_quarantined_before_the_cache_opens(tmp_path):
    repo, study = build(tmp_path)
    first = next(iter(site()))
    with pytest.raises(KeyboardInterrupt):
        go(repo, study, Opener(site(), fail={first: "interrupt"}))
    attempt = next((study / "attempts").iterdir())
    journal = attempt / "source" / "requests.jsonl"
    complete = journal.read_bytes()
    cut = b'{"at": "2026-10-02T21:00:00+00:00", "event": "request_sta'
    journal.write_bytes(complete + cut)  # as if a crash cut the cache's append short
    go(repo, study, Opener(site()), resume=attempt.name)
    meta = json.loads((attempt / "attempt.json").read_text())
    assert meta["status"] == "complete" and journal.read_bytes().startswith(complete)
    tail = meta["quarantined_journal_tail"][0]
    assert (attempt / "source" / "partial" / tail["file"]).read_bytes() == cut
    assert tail["bytes"] == len(cut) and tail["sha256"] == sha(cut)
    source = tmp_path / "source"
    source.mkdir()
    (source / "requests.jsonl").write_bytes(b'{"event": "request_started"}\nnot json\n')
    with pytest.raises(m.ProbeError, match="unreadable complete line"):
        m.quarantine_journal_tail(source, keep=print)


def test_ceiling_stop_written_before_its_record_survives_a_crash(tmp_path):
    repo, study = build(tmp_path)
    first = next(iter(site()))
    with pytest.raises(KeyboardInterrupt):
        go(repo, study, Opener(site(), fail={first: "interrupt"}))
    attempt = next((study / "attempts").iterdir())
    with pytest.raises(KeyboardInterrupt):
        go(repo, study, Opener(site(), fail={first: "interrupt"}), resume=attempt.name)
    with pytest.raises(m.ProbeError, match="(?i)attempt ceiling"):
        go(repo, study, Opener(site()), resume=attempt.name)
    record = attempt / "source" / "resources" / (sha(first.encode()) + ".json")
    record.unlink()  # as if the crash came after STOP.json but before the record
    with pytest.raises(m.ProbeError, match="acknowledge"):
        go(repo, study, Opener(site()), resume=attempt.name)
    go(repo, study, Opener(site()), resume=attempt.name, acknowledge_stop=True)
    assert json.loads(record.read_text())["status"] == "interrupted"
    assert json.loads((attempt / "attempt.json").read_text())["status"] == "complete"


def test_byte_ceiling_stops_once_then_fails_remaining_urls(tmp_path):
    repo, study = build(tmp_path, requests={"max_total_raw_bytes": 1})
    with pytest.raises(m.ProbeError, match="Halted"):
        go(repo, study, Opener(site()))  # the first response exceeds the allowance
    attempt = next((study / "attempts").iterdir())
    with pytest.raises(m.ProbeError, match="(?i)attempt ceiling"):
        go(repo, study, Opener(site()), resume=attempt.name, acknowledge_stop=True)
    opener = Opener(site())
    go(repo, study, opener, resume=attempt.name, acknowledge_stop=True)
    assert opener.calls == []
    rows = json.loads((attempt / "events.json").read_text())
    assert {r["event_status"] for r in rows} == {"exhibit_unavailable"}


def test_unbound_projection_must_match_records_json(tmp_path):
    repo, study = build(tmp_path)
    url = next(u for u in site() if u.endswith("ex991.pdf"))
    with pytest.raises(m.ProbeError, match="Halted"):
        go(repo, study, Opener(site(), fail={url: 429}))
    attempt = next((study / "attempts").iterdir())
    record = attempt / "attempt.json"
    meta = json.loads(record.read_text())
    del meta["projection_sha256"]
    record.write_text(json.dumps(meta))
    (attempt / "projection.json").write_text("{}")
    with pytest.raises(m.ProbeError, match="does not match records.json"):
        go(repo, study, Opener(site()), resume=attempt.name, acknowledge_stop=True)


def test_resume_waits_out_the_request_interval(tmp_path, monkeypatch):
    repo, study = build(tmp_path, requests={"minimum_request_interval_seconds": 1})
    naps = []
    monkeypatch.setattr(m.time, "sleep", lambda seconds: naps.append(seconds))
    url = next(u for u in site() if u.endswith("ex991.pdf"))
    with pytest.raises(m.ProbeError, match="Halted"):
        go(repo, study, Opener(site(), fail={url: 429}))
    attempt = next((study / "attempts").iterdir())
    naps.clear()
    go(repo, study, Opener(site()), resume=attempt.name, acknowledge_stop=True)
    assert naps and 0 < naps[0] <= 1


def test_resume_refuses_an_attempt_started_under_other_code(tmp_path):
    repo, study = build(tmp_path)
    url = next(u for u in site() if u.endswith("ex991.pdf"))
    with pytest.raises(m.ProbeError, match="Halted"):
        go(repo, study, Opener(site(), fail={url: 429}))
    attempt = next((study / "attempts").iterdir())
    probe = study / "probe.py"
    probe.write_bytes(probe.read_bytes() + b"# amended\n")
    freeze = json.loads((study / "freeze.json").read_text())
    freeze["code"][f".qualification/{m.STUDY}/probe.py"] = sha(probe.read_bytes())
    (study / "freeze.json").write_text(json.dumps(freeze))
    with pytest.raises(m.ProbeError, match="other code"):
        go(repo, study, Opener(site()), resume=attempt.name, acknowledge_stop=True)


def test_resume_binds_or_checks_the_projection_and_keeps_the_runtime(tmp_path):
    repo, study = build(tmp_path)
    url = next(u for u in site() if u.endswith("ex991.pdf"))
    with pytest.raises(m.ProbeError, match="Halted"):
        go(repo, study, Opener(site(), fail={url: 429}))
    attempt = next((study / "attempts").iterdir())
    record = attempt / "attempt.json"
    meta = json.loads(record.read_text())
    original = meta["runtime"]
    unbound = dict(meta)
    del unbound["projection_sha256"]  # as if the crash came before the hash was saved
    record.write_text(json.dumps(unbound))
    saved = (attempt / "projection.json").read_bytes()
    go(repo, study, Opener(site()), resume=attempt.name, acknowledge_stop=True)
    meta = json.loads(record.read_text())
    assert meta["status"] == "complete" and meta["projection_sha256"] == sha(saved)
    assert meta["runtime"] == original and meta["resumes"][0]["runtime"]
    args = (attempt.name, study / "definition.json", study / "freeze.json", repo, study)
    assert m.reanalyze(*args)["events_identical"]


def test_resume_refuses_a_changed_projection(tmp_path):
    repo, study = build(tmp_path)
    url = next(u for u in site() if u.endswith("ex991.pdf"))
    with pytest.raises(m.ProbeError, match="Halted"):
        go(repo, study, Opener(site(), fail={url: 429}))
    attempt = next((study / "attempts").iterdir())
    projection = attempt / "projection.json"
    projection.write_bytes(projection.read_bytes().replace(b"5200000", b"5200001"))
    with pytest.raises(m.ProbeError, match="Saved projection differs"):
        go(repo, study, Opener(site()), resume=attempt.name, acknowledge_stop=True)


def test_transport_failure_halts_once(tmp_path):
    repo, study = build(tmp_path)
    first = next(iter(site()))
    with pytest.raises(m.ProbeError, match="Transport failure"):
        go(repo, study, Opener(site(), fail={first: "transport"}))
    attempt = next((study / "attempts").iterdir())
    go(repo, study, Opener(site()), resume=attempt.name, acknowledge_stop=True)
    rows = {r["symbol"]: r for r in json.loads((attempt / "events.json").read_text())}
    assert rows["AAA"]["event_status"] == "exhibit_unavailable"


def test_interrupted_request_is_retried_once(tmp_path):
    repo, study = build(tmp_path)
    first = next(iter(site()))
    with pytest.raises(KeyboardInterrupt):
        go(repo, study, Opener(site(), fail={first: "interrupt"}))
    attempt = next((study / "attempts").iterdir())
    assert json.loads((attempt / "attempt.json").read_text())["status"] == "running"
    opener = Opener(site())
    go(repo, study, opener, resume=attempt.name)
    assert opener.calls[0] == first
    journal = (attempt / "source" / "requests.jsonl").read_text().splitlines()
    starts = [json.loads(x) for x in journal if '"request_started"' in x]
    assert [s["attempt"] for s in starts if s["url"] == first] == [1, 2]


def test_held_locks_and_changed_declaration_refuse_before_any_request(tmp_path):
    repo, study = build(tmp_path)
    for path in (study / "probe.lock.sqlite", repo / DEFINITION["paths"]["shared_source_lock"]):
        m.study_lock(study)
        holder = sqlite3.connect(path, isolation_level=None)
        holder.execute("BEGIN EXCLUSIVE")
        try:
            opener = Opener(site())
            with pytest.raises(m.ProbeError, match="held"):
                go(repo, study, opener)
            assert opener.calls == []
        finally:
            holder.execute("ROLLBACK")
            holder.close()
    (study / "definition.json").write_bytes((study / "definition.json").read_bytes() + b" ")
    with pytest.raises(m.ProbeError, match="frozen declaration"):
        go(repo, study, Opener(site()))
    assert not (study / "attempts").exists()


def test_missing_q_record_leaves_the_q_denominator(tmp_path):
    records = [dict(RECORD, accession=ids(i)[1], q_status="unavailable") for i in range(3)]
    repo, study = build(tmp_path, records=records)
    attempt = go(repo, study, Opener(site()))
    summary = json.loads((attempt / "summary.json").read_text())["all"]["signals"]
    assert summary["Q_flow"]["comparable"] == 0 and summary["S_flow"]["comparable"] == 3


def test_records_lacking_a_sampled_event_refuse_before_any_attempt_or_request(tmp_path):
    records = [dict(RECORD, accession=ids(i)[1]) for i in range(2)]  # the third is missing
    repo, study = build(tmp_path, records=records)
    opener = Opener(site())
    with pytest.raises(m.ProbeError, match="lacks sampled accessions"):
        go(repo, study, opener)
    assert opener.calls == [] and not (study / "attempts").exists()


def test_frozen_declaration_binds_this_code():
    frozen = json.loads((HERE / "freeze.json").read_text())
    assert frozen["definition_sha256"] == sha((HERE / "definition.json").read_bytes())
    assert set(frozen["code"]) == {
        m.AUDIT[0],
        m.CAPTURE[0],
        m.FEATURES[0],
        f".qualification/{m.STUDY}/probe.py",
        f".qualification/{m.STUDY}/test_probe.py",
    }
    for relative, digest in frozen["code"].items():
        assert sha((REPO / relative).read_bytes()) == digest
    assert m.declaration_problems(repo=REPO)[2] == []
