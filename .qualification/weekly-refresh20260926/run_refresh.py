"""Bounded recent-data capture; no model evaluation or broker calls."""
import hashlib
import json
import sqlite3
import threading
import traceback
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import httpx

from frontier.historical_data import read_history
from frontier.historical_lab import _save, run_historical_lab
from frontier.research_lab import completed_sessions
from frontier.research_universe import load_snapshot

REPO = Path(__file__).resolve().parents[2]
ROOT = Path(__file__).resolve().parent
WORKSPACE = ROOT / 'capture-workspace'
EXPECTED = '2026-09-25'
START = '2026-09-14'

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None

preserved = [
    REPO / 'data/historical/history-index.json',
    REPO / 'artifacts/historical-lab/latest.json',
    REPO / 'data/research/universe/latest.json',
    REPO / 'artifacts/historical-lab/runs/814780d48b4141b9a82a3fb917d1b85a/capture-index.json',
    REPO / 'artifacts/historical-lab/runs/90af4c840aad48f7ab58fba7a682f96a/capture-index.json',
]
before = {str(p.relative_to(REPO)): sha(p) for p in preserved}
started = datetime.now(timezone.utc).isoformat()
assert set(completed_sessions(started).values()) == {EXPECTED}
code_identity = {name: sha(REPO / 'src/frontier' / name) for name in (
    'historical_lab.py', 'historical_data.py', 'research_universe.py', 'research_lab.py'
)}
request = {
    'started_at': started, 'requested_start': START, 'expected_last_completed_session': EXPECTED,
    'capture_only': True, 'rediscover': True, 'isolated_workspace': str(WORKSPACE),
    'no_evaluation': True, 'no_model_build': True, 'no_main_index_update': True,
    'code_sha256': code_identity, 'main_state_before': before,
    'scope': 'Recent daily refresh and current dated directory snapshot, not full historical study.',
    'limitations': ['Current membership, not point-in-time historical membership.',
                   'Public provider daily bars and reported actions can be incomplete or revised.',
                   'Bounded recent window has insufficient warmup for trading decisions.',
                   'No automatic data promotion or performance conclusion.'],
}
_save(ROOT / 'request.json', request)
(WORKSPACE / 'config').mkdir(parents=True, exist_ok=True)
(WORKSPACE / 'config/scanner_universe.json').write_bytes((REPO / 'config/scanner_universe.json').read_bytes())
# Preserve response bytes even where the existing normalizer rejects a symbol.
# The original acquisition code and its own source records remain unchanged.
original_get = httpx.get
response_lock = threading.Lock()
response_root = ROOT / 'http-responses'
response_root.mkdir(exist_ok=True)
def retain_get(*args, **kwargs):
    response = original_get(*args, **kwargs)
    digest = hashlib.sha256(response.content).hexdigest()
    body = response_root / (digest + '.body')
    metadata = {'url': str(response.url), 'status_code': response.status_code,
                'sha256': digest, 'path': str(body.relative_to(ROOT)),
                'observed_at': datetime.now(timezone.utc).isoformat()}
    with response_lock:
        if not body.exists():
            body.write_bytes(response.content)
        with (ROOT / 'http-responses.jsonl').open('a', encoding='utf-8') as handle:
            handle.write(json.dumps(metadata, separators=(',', ':')) + '\n')
    return response
httpx.get = retain_get
lock = sqlite3.connect((REPO / 'data/historical/worker.lock.sqlite').as_uri() + '?mode=rw', uri=True, timeout=0)
try:
    lock.execute('BEGIN EXCLUSIVE')
    result = run_historical_lab(WORKSPACE, start=START, rediscover=True, capture_only=True)
    run_root = WORKSPACE / 'artifacts/historical-lab/runs' / result['run_id']
    records = json.loads((run_root / 'capture-index.json').read_text('utf-8'))
    failures = json.loads((run_root / 'capture-failures.json').read_text('utf-8'))
    manifest = load_snapshot(WORKSPACE)
    seen = set()
    totals = Counter()
    latest = Counter()
    latest_by_currency = Counter()
    stale = []
    for record in records:
        assert record['symbol'] not in seen
        seen.add(record['symbol'])
        frame = read_history(WORKSPACE / 'data/historical/capture-workspace', record)
        assert record['requested_start'] == START
        assert frame.session.min() >= START and frame.session.max() <= EXPECTED
        assert len(frame) == record['rows']
        assert frame.session.max() == record['last_session']
        totals['normalized_rows'] += len(frame)
        latest[record['last_session']] += 1
        latest_by_currency[f"{record['spec']['currency']}:{record['last_session']}"] += 1
        if record['last_session'] < EXPECTED:
            stale.append({'symbol': record['symbol'], 'last_session': record['last_session']})
    after = {str(p.relative_to(REPO)): sha(p) for p in preserved}
    assert before == after, 'Main historical state changed during isolated capture'
    response_count = 0
    for line in (ROOT / 'http-responses.jsonl').read_text('utf-8').splitlines():
        item = json.loads(line)
        assert sha(ROOT / item['path']) == item['sha256']
        response_count += 1
    summary = {**result, 'status': 'completed', 'completed_at': datetime.now(timezone.utc).isoformat(),
        'requested_start': START, 'last_completed_session': EXPECTED,
        'snapshot_id': manifest['snapshot_id'], 'listing_eligible': manifest['eligible_count'],
        'listing_sources': len(manifest['sources']), 'listing_counts': manifest['counts'],
        'captured_histories': len(records), 'failed_histories': len(failures),
        'normalized_rows': totals['normalized_rows'], 'last_session_counts': dict(latest),
        'last_session_by_currency': dict(latest_by_currency), 'stale_histories': stale,
        'http_responses_preserved': response_count, 'raw_hashes_verified': True,
        'main_state_unchanged': before == after, 'main_state_after': after,
        'limitations': request['limitations']}
    _save(ROOT / 'verification.json', summary)
    print(json.dumps(summary), flush=True)
except Exception as exc:
    _save(ROOT / 'failure.json', {'failed_at': datetime.now(timezone.utc).isoformat(),
          'error': str(exc), 'type': type(exc).__name__, 'traceback': traceback.format_exc()})
    raise
finally:
    httpx.get = original_get
    lock.close()
