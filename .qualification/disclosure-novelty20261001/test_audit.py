"""Synthetic boundaries only; never run the actual SEC corpus."""

import copy
import importlib.util
import json
import sqlite3
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock
from zoneinfo import ZoneInfo

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("cached_novelty_audit", HERE / "audit.py")
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)
ISSUER = {"symbol": "SYN", "cik": "0000000001"}
REQUEST = {"filed_from": "2012-01-01", "filed_through": "2025-12-31"}


def row(number=1, form="8-K", clock="2024-05-01T15:00:00Z", items="2.02", **changes):
    result = {
        "accessionNumber": f"0000000001-24-{number:06}",
        "form": form,
        "filingDate": "2024-05-01",
        "reportDate": "2024-03-31",
        "acceptanceDateTime": clock,
        "items": items,
    }
    result.update(changes)
    return result


def groups(rows):
    return audit.group_rows(
        ISSUER,
        [
            (value, {"source_path": "synthetic", "page_ordinal": 0, "row_ordinal": i})
            for i, value in enumerate(rows)
        ],
    )


def q_event(rows, clock="2024-05-02T15:00:00Z", manifest=None):
    q = row(99, form="10-Q", clock=clock)
    return audit.evaluate_event(
        ISSUER,
        q,
        groups([q])[0],
        manifest or {"status": "captured", "clock": {"synthetic": True}},
        groups(rows),
        REQUEST,
    )


class TimingTests(unittest.TestCase):
    def relation(self, q, k):
        return audit.time_relation(
            audit.api_clock({"acceptanceDateTime": q}), groups([row(clock=k)])[0]
        )

    def test_endpoints_and_microsecond_neighbors(self):
        q = datetime(2024, 5, 2, 15, tzinfo=timezone.utc)
        for seconds, micros, expected in [
            (-45 * 86400, 0, "preceding"),
            (-45 * 86400, -1, "outside_before"),
            (-1, 999999, "preceding"),
            (0, 0, "same_clock"),
            (0, 1, "late"),
            (7 * 86400, 0, "late"),
            (7 * 86400, 1, "outside_after"),
        ]:
            with self.subTest(seconds=seconds, micros=micros):
                stamp = (q + timedelta(seconds=seconds, microseconds=micros)).isoformat()
                self.assertEqual(self.relation(q.isoformat(), stamp)[0], expected)

    def test_equivalent_timezones_same_instant(self):
        self.assertEqual(
            self.relation("2024-05-02T15:00:00Z", "2024-05-02T11:00:00-04:00"), ("same_clock", 0)
        )

    def test_dst_elapsed_duration_not_civil_days(self):
        eastern = ZoneInfo("America/New_York")
        q = datetime(2024, 11, 10, 12, tzinfo=eastern)
        civil = q - timedelta(days=45)
        elapsed = q.astimezone(timezone.utc) - timedelta(seconds=45 * 86400)
        self.assertEqual(self.relation(q.isoformat(), civil.isoformat())[0], "outside_before")
        self.assertEqual(self.relation(q.isoformat(), elapsed.isoformat())[0], "preceding")

    def test_missing_invalid_naive_clocks(self):
        cases = [
            ({}, "missing"),
            ({"acceptanceDateTime": None}, "null"),
            ({"acceptanceDateTime": ""}, "empty"),
            ({"acceptanceDateTime": []}, "invalid_type"),
            ({"acceptanceDateTime": "2024-05-02T15:00:00"}, "naive"),
            ({"acceptanceDateTime": "2024-02-30T15:00:00Z"}, "invalid_encoding"),
        ]
        for value, expected in cases:
            with self.subTest(value=value):
                self.assertEqual(audit.api_clock(value)["status"], expected)
                self.assertEqual(
                    audit.time_relation(audit.api_clock(value), groups([row()])[0]),
                    ("unavailable", None),
                )

    def test_boundary_coverage_converts_endpoints_to_eastern(self):
        # UTC upper endpoint is2026-01-01; Eastern endpoint remains2025-12-31.
        clock = audit.api_clock({"acceptanceDateTime": "2025-12-25T00:30:00Z"})
        result = audit.window_coverage(clock, REQUEST)
        self.assertFalse(result["after_source_envelope"])
        clock = audit.api_clock({"acceptanceDateTime": "2025-12-25T06:00:00Z"})
        self.assertTrue(audit.window_coverage(clock, REQUEST)["after_source_envelope"])
        early = audit.api_clock({"acceptanceDateTime": "2012-01-10T15:00:00Z"})
        self.assertTrue(audit.window_coverage(early, REQUEST)["before_source_envelope"])
        unknown = audit.window_coverage(audit.api_clock({}), REQUEST)
        self.assertTrue(unknown["unknown"])
        self.assertIsNone(unknown["before_source_envelope"])
        self.assertFalse(unknown["complete_coverage_verified"])


class ItemAndGroupTests(unittest.TestCase):
    def test_exact_comma_trimmed_tokens(self):
        for text in ("2.02", " 2.02 , 9.01 ", "9.01,2.02", "2.02,2.02"):
            with self.subTest(text=text):
                self.assertEqual(audit.item_tokens({"items": text})["status"], "qualified_token")

    def test_malformed_substring_and_absent_items(self):
        cases = [
            ({}, "missing"),
            ({"items": None}, "null"),
            ({"items": "  "}, "empty"),
            ({"items": ["2.02"]}, "invalid_type"),
            ({"items": "2.02,"}, "invalid_encoding"),
            ({"items": "Item2.02"}, "invalid_encoding"),
            ({"items": "2.020"}, "invalid_encoding"),
            ({"items": "2.02;9.01"}, "invalid_encoding"),
            ({"items": "12.02"}, "valid_nonmatching"),
        ]
        for value, expected in cases:
            with self.subTest(value=value):
                self.assertEqual(audit.item_tokens(value)["status"], expected)

    def test_identical_duplicates_keep_both_raw_origins(self):
        value = row()
        result = groups([value, copy.deepcopy(value)])
        self.assertEqual(len(result), 1)
        self.assertEqual(len(result[0]["variants"]), 1)
        self.assertEqual(len(result[0]["variants"][0]["origins"]), 2)
        self.assertFalse(result[0]["conflicting_metadata"])

    def test_conflicts_preserve_variants_but_never_choose_winner(self):
        first, second = row(), row(items="9.01")
        result = groups([first, second])[0]
        self.assertTrue(result["conflicting_metadata"])
        self.assertEqual(len(result["variants"]), 2)
        self.assertIsNone(result["row"])
        self.assertEqual(result["items"]["status"], "conflicting_metadata")
        event, pairs = q_event([first, second])
        self.assertEqual(event["group_timing_counts"]["unavailable"], 1)
        self.assertEqual(len(event["unavailable_group_ids"]), 1)
        self.assertEqual(pairs, [])

    def test_json_type_differences_are_not_equal_duplicates(self):
        first, second = row(flag=True), row(flag=1)
        self.assertTrue(groups([first, second])[0]["conflicting_metadata"])


class EventTests(unittest.TestCase):
    def test_multiple_candidates_and_amendments_are_retained(self):
        event, pairs = q_event(
            [
                row(1),
                row(2),
                row(3, form="8-K/A"),
                row(4, items=None),
                row(5, items="2.020"),
                row(6, clock="2024-05-02T15:00:00Z"),
                row(7, clock="2024-05-03T15:00:00Z"),
            ]
        )
        self.assertEqual(event["status"], "multiple_preceding_candidates")
        self.assertEqual(len(event["preceding_candidate_ids"]), 2)
        self.assertEqual(len(pairs), 7)
        self.assertEqual(sum(pair["primary_candidate"] for pair in pairs), 2)
        self.assertEqual(event["amendment_item202_timing_counts"]["preceding"], 1)
        self.assertEqual(len(event["same_clock_item202_ids"]), 1)
        self.assertEqual(len(event["late_item202_ids"]), 1)

    def test_outside_and_unknown_evidence_without_cartesian_output(self):
        event, pairs = q_event(
            [
                row(1, clock="2013-01-01T15:00:00Z"),
                row(2, clock="2025-01-01T15:00:00Z"),
                row(3, clock=None),
            ]
        )
        self.assertEqual(pairs, [])
        self.assertEqual(event["group_timing_counts"]["outside_before"], 1)
        self.assertEqual(event["group_timing_counts"]["outside_after"], 1)
        self.assertEqual(event["group_timing_counts"]["unavailable"], 1)
        self.assertEqual(len(event["unavailable_group_ids"]), 1)
        self.assertEqual(event["status"], "no_observed_candidate")
        self.assertIsNone(event["unknown_undiscovered_disclosures"])

    def test_report_dates_never_prove_period_components_or_public_clock(self):
        _, pairs = q_event(
            [
                row(1),
                row(2, reportDate="2024-05-01"),
                row(3, reportDate=None),
                row(4, reportDate="not-a-date"),
            ]
        )
        self.assertEqual(
            [pair["reportDate_relation"] for pair in pairs],
            ["equal_metadata_dates", "different_metadata_dates", "unavailable", "unavailable"],
        )
        for pair in pairs:
            self.assertFalse(pair["fiscal_period_verified"])
            self.assertFalse(pair["disclosed_components_verified"])
            self.assertFalse(pair["public_dissemination_instant_verified"])

    def test_failed_original_q_manifest_is_annotation_not_deletion(self):
        manifest = {"status": "incomplete", "error": "HTTP503", "clock": None}
        event, pairs = q_event([row()], manifest=manifest)
        self.assertEqual(event["manifest_annotation"], manifest)
        self.assertEqual(len(pairs), 1)
        self.assertEqual(len(event["preceding_candidate_ids"]), 1)
        self.assertNotIn("S", event)
        self.assertNotIn("Q", event)

    def test_missing_q_clock_preserves_event_and_all_unknown_references(self):
        event, pairs = q_event([row(1), row(2)], clock=None)
        self.assertEqual(event["status"], "q_clock_unavailable")
        self.assertEqual(event["group_timing_counts"]["unavailable"], 2)
        self.assertEqual(len(event["unavailable_group_ids"]), 2)
        self.assertEqual(pairs, [])

    def test_all_issuer_year_denominators_including_zero_and_failed(self):
        event, _ = q_event(
            [row()], manifest={"status": "incomplete", "error": "HTTP503", "clock": None}
        )
        fixed = {
            **ISSUER,
            "requested_originals": 1,
            "filed_year_counts": {str(year): int(year == 2024) for year in range(2012, 2026)},
            "unknown_undiscovered_originals": None,
            "source_window_complete_flag": True,
        }
        result = audit.issuer_year_denominators({"issuer_denominators": [fixed]}, [event])
        self.assertEqual(len(result), 14)
        self.assertEqual(sum(value["requested_originals"] for value in result), 1)
        current = next(value for value in result if value["filed_year"] == 2024)
        self.assertEqual(current["manifest_status_counts"], {"incomplete": 1})
        self.assertIsNone(current["unknown_undiscovered_originals"])


class SourceTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="frontier-novelty-synthetic-")
        self.addCleanup(self.temporary.cleanup)
        self.repo = Path(self.temporary.name)
        self.source = self.repo / "source"
        (self.source / "raw").mkdir(parents=True)
        self.q = row(99, form="10-Q", clock="2024-05-02T15:00:00Z")
        self.k = row(1)
        self.history_descriptor = {
            "name": "CIK0000000001-submissions-001.json",
            "filingFrom": "2024-01-01",
            "filingTo": "2024-12-31",
        }
        self.root_body = {
            "cik": 1,
            "tickers": ["SYN"],
            "filings": {"recent": self.table([self.q, self.k]), "files": [self.history_descriptor]},
        }
        self.history_body = self.table([self.k])
        self.request = {**REQUEST, "issuers": [ISSUER]}
        audit.write(self.source / "request.json", self.request)
        self.definition = {
            "source_root": "source",
            "membership": [ISSUER],
            "requested_originals": 1,
            "requested_events": [
                {
                    "symbol": "SYN",
                    "cik": ISSUER["cik"],
                    "accession": self.q["accessionNumber"],
                    "filingDate": self.q["filingDate"],
                    "reportDate": self.q["reportDate"],
                }
            ],
            "raw_discovery_unique_inputs": 2,
        }
        self.refresh()

    @staticmethod
    def table(rows):
        return {key: [value[key] for value in rows] for key in rows[0]}

    def refresh(self):
        sources = []
        declarations = []
        for number, body in enumerate((self.root_body, self.history_body)):
            name = "root.json" if number == 0 else "history.json"
            path = self.source / "raw" / name
            path.write_text(json.dumps(body), encoding="utf-8")
            url = (
                "https://data.sec.gov/submissions/CIK0000000001.json"
                if number == 0
                else "https://data.sec.gov/submissions/" + self.history_descriptor["name"]
            )
            meta = {
                "url": url,
                "path": path.relative_to(self.repo).as_posix() if number == 0 else "raw/" + name,
                "reused": number == 0,
                "status": 200,
                "sha256": audit.sha(path),
                "bytes": path.stat().st_size,
            }
            sources.append(meta)
            declarations.append(
                {
                    **ISSUER,
                    "url": url,
                    "path": path.relative_to(self.repo).as_posix(),
                    "sha256": meta["sha256"],
                    "bytes": meta["bytes"],
                }
            )
        self.definition["discovery_sources"] = declarations
        discovery = {
            "complete": True,
            "error": None,
            "sources": sources,
            "rows": [self.q, self.k, self.k],
            "original_accessions": [self.q],
        }
        registry = {
            "complete": True,
            "request_sha256": audit.sha(self.source / "request.json"),
            "issuers": [{"issuer": ISSUER, "discovery": discovery}],
        }
        (self.source / "registry.json").write_text(json.dumps(registry), encoding="utf-8")

    def reconstruct(self):
        return audit.reconstruct_discovery(
            self.definition, self.repo, audit.load_parser(audit.REPO)
        )

    def test_repo_relative_source_without_reused_flag(self):
        meta = {"path": ".qualification/synthetic/raw.json", "reused": False}
        self.assertEqual(
            audit.source_path(self.repo, self.source, meta),
            self.repo / ".qualification/synthetic/raw.json",
        )

    def test_absolute_and_escaping_source_paths_refused(self):
        with self.assertRaisesRegex(ValueError, "Absolute"):
            audit.source_path(self.repo, self.source, {"path": str(self.source / "raw/root.json")})
        with self.assertRaises(ValueError):
            audit.source_path(self.repo, self.source, {"path": "../../outside.json"})

    def test_raw_reconstruction_keeps_page_row_and_identical_origins(self):
        originals, metadata, _ = self.reconstruct()
        self.assertEqual(len(originals), 1)
        self.assertEqual(len(metadata), 1)
        origins = metadata[0]["variants"][0]["origins"]
        self.assertEqual(
            [(value["page_ordinal"], value["row_ordinal"]) for value in origins], [(0, 1), (1, 0)]
        )
        self.assertEqual(origins[1]["history_descriptor"], self.history_descriptor)

    def test_corrupt_raw_hash_refused(self):
        with (self.source / "raw/root.json").open("ab") as stream:
            stream.write(b" ")
        with self.assertRaisesRegex(ValueError, "raw identity"):
            self.reconstruct()

    def test_root_cik_and_ticker_refused(self):
        for key, value in (("cik", 2), ("tickers", ["OTHER"])):
            with self.subTest(key=key):
                original = self.root_body[key]
                self.root_body[key] = value
                self.refresh()
                with self.assertRaisesRegex(ValueError, "CIK/ticker"):
                    self.reconstruct()
                self.root_body[key] = original

    def test_history_cik_route_and_descriptor_refused(self):
        self.history_descriptor["name"] = "CIK0000000002-submissions-001.json"
        self.refresh()
        with self.assertRaisesRegex(ValueError, "descriptor CIK"):
            self.reconstruct()

    def test_reversed_history_descriptor_refused(self):
        self.history_descriptor["filingFrom"] = "2025-01-01"
        self.refresh()
        with self.assertRaisesRegex(ValueError, "Reversed"):
            self.reconstruct()

    def test_parallel_array_mismatch_is_not_swallowed(self):
        self.history_body["items"].append("2.02")
        self.refresh()
        with self.assertRaisesRegex(Exception, "parallel arrays"):
            self.reconstruct()

    def test_registry_raw_row_mismatch_refused(self):
        registry = audit.read(self.source / "registry.json")
        registry["issuers"][0]["discovery"]["rows"][1]["items"] = "9.01"
        (self.source / "registry.json").write_text(json.dumps(registry), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "table/registry"):
            self.reconstruct()

    def test_requested_original_denominator_mismatch_refused(self):
        self.definition["requested_originals"] = 2
        with self.assertRaisesRegex(ValueError, "denominator"):
            self.reconstruct()

    def test_input_identity_change_refused(self):
        identities = {"source/request.json": audit.sha(self.source / "request.json")}
        audit.verify_inputs(self.repo, identities)
        (self.source / "request.json").write_text("{}", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "Bound input changed"):
            audit.verify_inputs(self.repo, identities)

    def test_source_read_guard_blocks_owned_exclusive_writer(self):
        path = self.source / "capture.lock.sqlite"
        connection = sqlite3.connect(path)
        connection.execute("CREATE TABLE fixture(value)")
        connection.commit()
        with audit.readonly_lock(path):
            with self.assertRaises(sqlite3.OperationalError):
                connection.execute("BEGIN EXCLUSIVE")
        connection.execute("BEGIN EXCLUSIVE")
        with self.assertRaises(sqlite3.OperationalError):
            with audit.readonly_lock(path):
                self.fail("active writer must refuse reader")
        connection.rollback()
        connection.close()

    def test_absent_lock_never_created_by_reader(self):
        path = self.source / "missing.sqlite"
        with self.assertRaisesRegex(ValueError, "lock missing"):
            with audit.readonly_lock(path):
                pass
        self.assertFalse(path.exists())

    def test_parser_import_never_constructs_network_transport(self):
        with mock.patch("urllib.request.build_opener", side_effect=AssertionError("no transport")):
            parser = audit.load_parser(audit.REPO)
            self.assertEqual(len(parser(self.table([self.q]))), 1)


class DurableFailureTests(unittest.TestCase):
    def test_invalid_definition_attempt_has_durable_failure_without_overwrite(self):
        with tempfile.TemporaryDirectory(prefix="frontier-novelty-failure-") as directory:
            repo = Path(directory)
            definition, implementation = repo / "bad-definition.json", repo / "implementation.json"
            audit.write(definition, {"synthetic": True})
            audit.write(implementation, {"synthetic": True})
            original = definition.read_bytes()
            with self.assertRaisesRegex(ValueError, "definition changed"):
                audit.run(definition, implementation, repo=repo, output_root=repo / "audit")
            attempts = list((repo / "audit/attempts").iterdir())
            self.assertEqual(len(attempts), 1)
            self.assertTrue((attempts[0] / "attempt.json").is_file())
            self.assertEqual(audit.read(attempts[0] / "failure.json")["status"], "failed")
            self.assertFalse((attempts[0] / "completion.json").exists())
            self.assertEqual(definition.read_bytes(), original)
            with self.assertRaises(FileExistsError):
                audit.write(attempts[0] / "failure.json", {"overwrite": True})

    def test_json_duplicate_keys_and_nonfinite_values_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "synthetic.json"
            for text in ('{"a":1,"a":2}', '{"a":NaN}'):
                with self.subTest(text=text):
                    path.write_text(text, encoding="utf-8")
                    with self.assertRaises(ValueError):
                        audit.read(path)


if __name__ == "__main__":
    unittest.main()
