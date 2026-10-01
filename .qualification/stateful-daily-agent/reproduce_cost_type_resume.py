"""Qualification-only reproduction of int/float cost input resume mismatch."""
import json
import runpy
import sqlite3
from pathlib import Path
from uuid import uuid4

import pytest
from frontier import candidate_replay as replay
from frontier.execution_costs import get_cost_profile

base = Path('.qualification/stateful-daily-agent')
workspace = base / ('cost-type-repro-' + uuid4().hex)
monkeypatch = pytest.MonkeyPatch()
prepared = runpy.run_path('tests/test_candidate_replay.py')['rehearsal'].__wrapped__(monkeypatch)
try:
    first = replay.replay_candidate(workspace, 'a' * 32, chunk_sessions=2, max_chunks=1)
    failure = None
    try:
        replay.replay_candidate(workspace, 'a' * 32, replay_id=first['replay_id'],
                               round_trip_bps=40.0, chunk_sessions=3)
    except ValueError as exc:
        failure = str(exc)
    assert failure == 'Resume cursor, market or policy differs from saved account', failure
    resumed = replay.replay_candidate(workspace, 'a' * 32, replay_id=first['replay_id'],
                                     round_trip_bps=40, chunk_sessions=3)
    assert resumed['status'] == 'complete'
    int_spec, float_spec = get_cost_profile('proportional', 40).specification, get_cost_profile('proportional', 40.0).specification
    assert int_spec == float_spec
    assert json.dumps(int_spec, sort_keys=True) != json.dumps(float_spec, sort_keys=True)
    journal = workspace/'artifacts/candidate-replays'/first['replay_id']/'journal.sqlite'
    connection = sqlite3.connect(journal.resolve().as_uri()+'?mode=ro', uri=True)
    attempts = connection.execute('SELECT status,error,request FROM attempts ORDER BY started_at').fetchall()
    result = dict(confirmed=True, workspace=str(workspace), replay_id=first['replay_id'],
                  integer_and_float_specs_compare_equal=True, serialized_scope_differs=True,
                  api_default_to_cli_equivalent_failure=failure,
                  integer_resume_control_status=resumed['status'],control_completed_trades=resumed['trades'],
                  attempts=[dict(status=s,error=e,request=json.loads(r)) for s,e,r in attempts])
    (base/'cost-type-resume-repro.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result),flush=True)
finally:
    monkeypatch.undo()
