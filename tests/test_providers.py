"""Exercise the provider against a separate CLI process and its event protocol."""

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

from frontier.providers import CodexProvider, ProviderError

SCHEMA = {
    "type": "object",
    "properties": {"name": {"type": "string"}},
    "required": ["name"],
    "additionalProperties": False,
}


@pytest.fixture
def fake_cli(tmp_path: Path) -> list[str]:
    script = tmp_path / "cli.py"
    script.write_text(
        """
import json
import os
import pathlib
import sys
import time

args = sys.argv[1:]
if args == ['--version']:
    print('codex-cli 0.fixture')
elif args == ['login', 'status']:
    print('Logged in using ChatGPT')
elif args[0] == 'exec':
    pathlib.Path('invocation.json').write_text(json.dumps({
        'args': args,
        'prompt': sys.stdin.read(),
        'api_key_present': 'OPENAI_API_KEY' in os.environ,
    }))
    mode = os.environ.get('PROVIDER_FIXTURE_MODE', 'success')
    if mode == 'timeout':
        time.sleep(3)
    if mode == 'child_timeout':
        child = __import__('subprocess').Popen(
            [sys.executable, '-c', 'import time; time.sleep(20)'])
        pathlib.Path('child.pid').write_text(str(child.pid))
        time.sleep(20)
    if mode == 'nonzero':
        print(json.dumps({'type': 'turn.failed', 'error': 'fixture failure'}))
        print('fixture stderr', file=sys.stderr)
        sys.exit(17)
    output = pathlib.Path(args[args.index('-o') + 1])
    output.write_text(json.dumps({'name': 'example'}))
    print(json.dumps({'type': 'thread.started', 'thread_id': 'fixture'}))
    item_type = 'command_execution' if mode == 'tool' else 'agent_message'
    print(json.dumps({'type': 'item.completed', 'item': {'type': item_type}}))
    print(json.dumps({'type': 'turn.completed', 'usage': {
        'input_tokens': 11, 'output_tokens': 3, 'cached_input_tokens': 2}}))
else:
    sys.exit(2)
""".strip(),
        encoding="utf-8",
    )
    return [sys.executable, str(script)]


def test_success_persists_protocol_and_scrubs_api_key(fake_cli, tmp_path, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "never-export-this")
    artifacts = tmp_path / "proposal"
    result = CodexProvider(cli_command=fake_cli).propose("give one name", SCHEMA, artifacts)

    invocation = json.loads((artifacts / "invocation.json").read_text())
    assert invocation["prompt"] == "give one name"
    assert invocation["api_key_present"] is False
    assert invocation["args"][-1] == "-"
    assert "--ignore-user-config" in invocation["args"]
    assert "--disable" in invocation["args"]
    assert result["proposal"] == {"name": "example"}
    assert result["usage"]["input_tokens"] == 11
    assert result["auth_method"] == "ChatGPT"
    assert result["cli_version"] == "codex-cli 0.fixture"
    assert result["event_log"] == artifacts / "events.jsonl"
    metadata = json.loads((artifacts / "metadata.json").read_text())
    assert metadata["status"] == "succeeded"
    assert metadata["charge_usd"] is None
    assert metadata["prompt_sha256"]
    assert metadata["output_sha256"]


@pytest.mark.parametrize("mode", ["nonzero", "tool", "timeout"])
def test_failure_retains_artifacts(fake_cli, tmp_path, monkeypatch, mode):
    monkeypatch.setenv("PROVIDER_FIXTURE_MODE", mode)
    artifacts = tmp_path / mode
    with pytest.raises(ProviderError) as error:
        CodexProvider(cli_command=fake_cli).propose(
            "give one name", SCHEMA, artifacts, timeout_seconds=1 if mode == "timeout" else 5
        )
    assert error.value.artifact_path == artifacts
    failure = json.loads((artifacts / "failure.json").read_text())
    assert failure["status"] == ("timed_out" if mode == "timeout" else "failed")
    assert (artifacts / "prompt.txt").read_text() == "give one name"
    assert (artifacts / "schema.json").is_file()
    if mode == "nonzero":
        assert failure["exit_code"] == 17
        assert "fixture stderr" in (artifacts / "stderr.txt").read_text()
    if mode == "tool":
        assert "command_execution" in (artifacts / "events.jsonl").read_text()


def test_loose_schema_is_recorded_as_failure(fake_cli, tmp_path):
    artifacts = tmp_path / "invalid"
    with pytest.raises(ProviderError, match="additionalProperties"):
        CodexProvider(cli_command=fake_cli).propose(
            "give one name", {"type": "object", "properties": {}}, artifacts
        )
    assert (artifacts / "failure.json").is_file()
    assert not (artifacts / "invocation.json").exists()


def test_timeout_terminates_owned_child(fake_cli, tmp_path, monkeypatch):
    monkeypatch.setenv("PROVIDER_FIXTURE_MODE", "child_timeout")
    artifacts = tmp_path / "tree"
    with pytest.raises(ProviderError):
        CodexProvider(cli_command=fake_cli).propose(
            "give one name", SCHEMA, artifacts, timeout_seconds=1
        )
    pid = int((artifacts / "child.pid").read_text())
    assert json.loads((artifacts / "failure.json").read_text())["timed_out"] is True
    if os.name == "nt":
        # tasklist reports the PID only while the process remains alive.
        for _ in range(10):
            listing = subprocess.run(
                ["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"],
                capture_output=True, text=True, check=True,
            ).stdout
            if f'"{pid}"' not in listing:
                break
            time.sleep(0.1)
        assert f'"{pid}"' not in listing
    else:
        with pytest.raises(ProcessLookupError):
            os.kill(pid, 0)
