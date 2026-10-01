"""Offline split/ADS event inventory; never reads strategy outputs or changes sources."""
from bisect import bisect_left
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from statistics import median
from zoneinfo import ZoneInfo
import csv
import hashlib
import json
import math
import time

ROOT = Path(__file__).resolve().parent
WORKSPACE = ROOT.parent.parent
SOURCE_ROOT = WORKSPACE / 'data/historical/capture-workspace'
RUN_ROOT = WORKSPACE / 'artifacts/historical-lab/runs/90af4c840aad48f7ab58fba7a682f96a'
LOCAL = ZoneInfo('America/Toronto')

def digest(raw):
    return hashlib.sha256(raw).hexdigest()

def number(value):
    try:
        value = float(value)
        return value if math.isfinite(value) else None
    except (ValueError, TypeError):
        return None

def session(stamp):
    return datetime.fromtimestamp(float(stamp), timezone.utc).astimezone(LOCAL).date().isoformat()

def write_json(name, value):
    (ROOT / name).write_text(json.dumps(value, indent=2, allow_nan=False), encoding='utf-8')

def write_csv(name, rows):
    fields = list(dict.fromkeys(key for row in rows for key in row))
    with (ROOT / name).open('w', encoding='utf-8', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)

def at(values, index):
    return number(values[index]) if index is not None and index < len(values) else None

def snapshot(result, dates, index, events):
    if index is None or index >= len(dates):
        return {}
    quote = result['indicators']['quote'][0]
    adjusted = result['indicators'].get('adjclose', [{}])[0].get('adjclose', [])
    factor = math.prod(item['ratio'] for item in events if item['session'] > dates[index])
    close, volume = at(quote.get('close', []), index), at(quote.get('volume', []), index)
    adj = at(adjusted, index)
    return {
        'session': dates[index], 'timestamp': result['timestamp'][index],
        'provider_close': close, 'provider_adjclose': adj, 'provider_volume': volume,
        'provider_high': at(quote.get('high', []), index),
        'provider_low': at(quote.get('low', []), index),
        'reported_later_split_factor': factor,
        'reconstructed_nominal_close': close * factor if close is not None else None,
        'reconstructed_nominal_volume': volume / factor if volume is not None and factor > 0 else None,
        'provider_adjusted_to_close': adj / close if adj is not None and close is not None and close > 0 else None,
    }

def process(record):
    path = (SOURCE_ROOT / record['path']).resolve()
    if not path.is_relative_to((SOURCE_ROOT / 'data/scanner/raw').resolve()):
        raise ValueError('Source outside original raw directory')
    raw = path.read_bytes()
    if digest(raw) != record['sha256']:
        raise ValueError('Frozen source hash mismatch')
    payload = json.loads(raw)
    result = payload['chart']['result'][0]
    if result['meta']['symbol'].upper() != record['symbol'].upper():
        raise ValueError('Source symbol mismatch')
    splits = result.get('events', {}).get('splits', {})
    capture_date = datetime.fromisoformat(record['captured_at']).astimezone(LOCAL).date().isoformat()
    cutoff_date = datetime.fromisoformat(record.get('requested_as_of', record['captured_at'])).astimezone(LOCAL).date().isoformat()
    valid_events, invalid_events = [], []
    for event_key, event in splits.items():
        try:
            numerator, denominator = number(event['numerator']), number(event['denominator'])
            if numerator is None or denominator is None or min(numerator, denominator) <= 0:
                raise ValueError('Invalid positive split components')
            item = {'key': event_key, 'session': session(event['date']), 'ratio': numerator / denominator}
            if item['session'] <= capture_date:
                valid_events.append(item)
        except (KeyError, TypeError, ValueError, OverflowError) as exc:
            invalid_events.append({'key': event_key, 'error': str(exc)})
    duplicates = sorted(date for date, count in Counter(x['session'] for x in valid_events).items() if count > 1)
    coverage = {'symbol': record['symbol'], 'currency': record['spec']['currency'], 'sha256': record['sha256'],
                'path': record['path'], 'captured_at': record['captured_at'], 'status': 'verified',
                'raw_split_count': len(splits), 'raw_dividend_count': len(result.get('events', {}).get('dividends', {})),
                'invalid_split_count': len(invalid_events), 'duplicate_effective_sessions': '|'.join(duplicates),
                'raw_bar_count': len(result.get('timestamp', [])), 'frozen_normalized_rows': record['rows']}
    if not splits:
        return coverage, []
    dates = [session(x) for x in result.get('timestamp', [])]
    if dates != sorted(dates) or len(set(dates)) != len(dates):
        raise ValueError('Unordered or duplicate source bar sessions')
    rows = []
    invalid_by_key = {x['key']: x['error'] for x in invalid_events}
    for event_key, event in splits.items():
        row = {'symbol': record['symbol'], 'currency': record['spec']['currency'], 'calendar': record['spec']['calendar'],
               'source_sha256': record['sha256'], 'source_path': record['path'], 'source_url': record['url'],
               'captured_at': record['captured_at'], 'requested_as_of': record.get('requested_as_of'),
               'event_key': event_key, 'event_raw_json': json.dumps(event, separators=(',', ':')),
               'nominal_convention_status': 'reported-factor reconstruction; unverified provider convention',
               'source_has_duplicate_event_sessions': bool(duplicates)}
        if event_key in invalid_by_key:
            row.update(status='invalid_event', failure=invalid_by_key[event_key]); rows.append(row); continue
        effective = session(event['date'])
        ratio = float(event['numerator']) / float(event['denominator'])
        direction = 'forward' if ratio > 1 else 'reverse' if ratio < 1 else 'neutral'
        position = bisect_left(dates, effective)
        exact = position if position < len(dates) and dates[position] == effective else None
        previous = position - 1 if position > 0 else None
        next_index = position if position < len(dates) else None
        row.update(status='valid_event', effective_session=effective, numerator=float(event['numerator']),
                   denominator=float(event['denominator']), new_shares_per_old=ratio, direction=direction,
                   effective_by_capture=effective <= capture_date, effective_by_cutoff=effective <= cutoff_date,
                   exact_effective_bar=exact is not None, prior_bar=previous is not None,
                   nominal_reconstruction_has_invalid_other_events=bool(invalid_events))
        for prefix, index in [('prior', previous), ('effective', exact), ('on_or_after', next_index)]:
            row.update({prefix + '_' + key: value for key, value in snapshot(result, dates, index, valid_events).items()})
        quote = result['indicators']['quote'][0]
        dollar_volumes = []
        for index in range(max(0, position - 20), position):
            close, volume = at(quote.get('close', []), index), at(quote.get('volume', []), index)
            if close is not None and volume is not None and close > 0 and volume > 0:
                dollar_volumes.append(close * volume)
        liquidity = median(dollar_volumes) if len(dollar_volumes) >= 10 else None
        row.update(prior20_liquidity_observations=len(dollar_volumes), prior20_native_dollar_volume_proxy=liquidity)
        a, b = row.get('prior_provider_adjclose'), row.get('effective_provider_adjclose')
        if a is not None and b is not None and min(a, b) > 0:
            change = b / a
            row.update(adjusted_close_ratio=change, adjusted_return=change - 1,
                       large_adjusted_move_triage=abs(math.log(change)) >= math.log(1.5),
                       reverse_factor_alignment_log_distance=abs(math.log(change * ratio)))
            row['ratio_alignment_triage'] = row['large_adjusted_move_triage'] and abs(math.log(change * ratio)) <= math.log(1.2)
        else:
            row.update(large_adjusted_move_triage=False, ratio_alignment_triage=False)
        row['missing_boundary_reason'] = '|'.join(reason for ok, reason in [(previous is not None, 'no_prior_bar'), (exact is not None, 'no_effective_bar'), (a is not None and a > 0, 'missing_positive_prior_adjusted'), (b is not None and b > 0, 'missing_positive_effective_adjusted')] if not ok)
        rows.append(row)
    return coverage, rows

def choose_sample(rows, definition):
    groups = {}
    seed = definition['followup_sample']['seed']
    for row in rows:
        if row['status'] != 'valid_event' or row['currency'] not in ('USD', 'CAD') or row['direction'] == 'neutral' or not row['effective_by_cutoff']:
            continue
        year = int(row['effective_session'][:4])
        era = '<=2009' if year <= 2009 else '2010-2019' if year <= 2019 else '2020-2023' if year <= 2023 else '2024-2026'
        magnitude = max(row['new_shares_per_old'], 1 / row['new_shares_per_old'])
        size = '<=2' if magnitude <= 2 else '>2'
        liquidity = row['prior20_native_dollar_volume_proxy']
        activity = 'unavailable' if liquidity is None else '<1000000' if liquidity < 1_000_000 else '>=1000000'
        cell = '|'.join([row['currency'], row['direction'], era, size, activity])
        identity = f"{seed}|{row['symbol']}|{row['effective_session']}|{row['numerator']}:{row['denominator']}"
        rank = digest(identity.encode())
        groups.setdefault(cell, []).append((rank, row))
    sample = []
    strata = []
    for cell, candidates in sorted(groups.items()):
        rank, selected = min(candidates, key=lambda pair: pair[0])
        sample.append({'stratum': cell, 'stratum_events': len(candidates), 'sample_rank_sha256': rank, **selected})
        strata.append({'stratum': cell, 'eligible_events': len(candidates), 'selected_symbol': selected['symbol'], 'selected_session': selected['effective_session'], 'rank': rank})
    return sample, strata

def main():
    started = time.monotonic()
    definition = json.loads((ROOT / 'definition.json').read_text())
    index_raw = (RUN_ROOT / 'capture-index.json').read_bytes()
    assert digest(index_raw) == definition['capture_index_sha256']
    records = json.loads(index_raw)
    assert not (ROOT / 'events.jsonl').exists(), 'Preserve the previous attempt; inspect before resuming'
    rows, coverage, failures = [], [], []
    with (ROOT / 'events.jsonl').open('w', encoding='utf-8') as event_file, (ROOT / 'source-coverage.jsonl').open('w', encoding='utf-8') as source_file:
        for count, record in enumerate(records, 1):
            try:
                source, events = process(record)
                coverage.append(source); rows.extend(events)
                source_file.write(json.dumps(source, allow_nan=False) + '\n')
                for event in events:
                    event_file.write(json.dumps(event, allow_nan=False) + '\n')
            except Exception as exc:
                failure = {'symbol': record['symbol'], 'source_sha256': record['sha256'], 'error_type': type(exc).__name__, 'error': str(exc)}
                failures.append(failure)
                source_file.write(json.dumps({'status': 'failed', **failure}) + '\n')
            if count % 500 == 0:
                event_file.flush(); source_file.flush()
                print(json.dumps({'processed_sources': count, 'events': len(rows), 'failures': len(failures), 'seconds': round(time.monotonic() - started, 1)}), flush=True)
    sample, strata = choose_sample(rows, definition)
    write_csv('events.csv', rows); write_csv('validation-sample.csv', sample); write_csv('sample-strata.csv', strata)
    write_csv('triage-flags.csv', [row for row in rows if row.get('large_adjusted_move_triage') or row.get('missing_boundary_reason') or row['status'] != 'valid_event'])
    write_json('failures.json', failures)
    capture_failures_raw = (RUN_ROOT / 'capture-failures.json').read_bytes()
    (ROOT / 'original-capture-failures.json').write_bytes(capture_failures_raw)
    summary = {
        'completed_at': datetime.now(timezone.utc).isoformat(), 'seconds': time.monotonic() - started,
        'requested_usable_sources': len(records), 'verified_source_count': len(coverage), 'source_failures': len(failures),
        'sources_with_reported_splits': sum(c['raw_split_count'] > 0 for c in coverage),
        'events': len(rows), 'event_status': dict(Counter(r['status'] for r in rows)),
        'directions': dict(Counter(r.get('direction', 'invalid') for r in rows)),
        'currencies': dict(Counter(r['currency'] for r in rows)),
        'source_currencies': dict(Counter(r['currency'] for r in coverage)),
        'missing_boundaries': sum(bool(r.get('missing_boundary_reason')) for r in rows),
        'large_adjusted_move_triage': sum(bool(r.get('large_adjusted_move_triage')) for r in rows),
        'ratio_alignment_triage': sum(bool(r.get('ratio_alignment_triage')) for r in rows),
        'validation_sample_count': len(sample), 'maximum_predeclared_sample_cells': 96,
        'original_failed_instruments_unavailable': len(json.loads(capture_failures_raw)),
        'original_capture_failures_sha256': digest(capture_failures_raw),
        'definition_sha256': digest((ROOT / 'definition.json').read_bytes()),
        'script_sha256': digest(Path(__file__).read_bytes()),
        'normalizer_reference_sha256': digest((WORKSPACE / 'src/frontier/historical_data.py').read_bytes()),
        'qualification': 'Provider-event inventory and independently predeclared sample, not verified action completeness or corrected performance',
    }
    assert len(sample) <= 96
    assert sum(c['raw_split_count'] for c in coverage) == len(rows)
    write_json('summary.json', summary)
    write_json('inventory.json', [{'file': p.name, 'sha256': digest(p.read_bytes()), 'bytes': p.stat().st_size} for p in sorted(ROOT.iterdir()) if p.is_file() and p.name != 'inventory.json'])
    print(json.dumps(summary, indent=2))

if __name__ == '__main__':
    main()
