"""A narrow, auditable Codex CLI adapter for structured research proposals."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import signal
import subprocess
import time
from pathlib import Path
from typing import Any, Sequence


class ProviderError(RuntimeError):
    """A failed provider call whose evidence remains in ``artifact_path``."""

    def __init__(self, message: str, artifact_path: Path):
        super().__init__(message)
        self.artifact_path = artifact_path


def _cli_command() -> list[str]:
    """Resolve a native executable or an npm shim without invoking a shell."""
    if os.name == "nt":
        # Python's which does not resolve .ps1 on installations whose PATHEXT omits it.
        for directory in os.environ.get("PATH", "").split(os.pathsep):
            entry = (
                Path(directory) / "node_modules" / "@openai" / "codex" / "bin" / "codex.js"
            )
            node = shutil.which("node.exe")
            if (Path(directory) / "codex.ps1").is_file() and entry.is_file() and node:
                return [node, str(entry)]
        launcher = shutil.which("codex.exe")
        if launcher:
            return [launcher]
    else:
        launcher = shutil.which("codex")
        if launcher:
            return [launcher]
    raise RuntimeError("Codex CLI was not found as a directly executable installation")


def _strict_schema(schema: dict[str, Any]) -> None:
    """Reject schemas that the observed structured-output CLI route cannot accept."""
    if schema.get("type") != "object" or schema.get("additionalProperties") is not False:
        raise ValueError("proposal schema must be an object with additionalProperties: false")
    properties = schema.get("properties")
    if not isinstance(properties, dict) or set(schema.get("required", [])) != set(properties):
        raise ValueError("proposal schema must require every declared property")

    def visit(value: Any) -> None:
        if not isinstance(value, dict):
            return
        if value.get("type") == "object" and value.get("additionalProperties") is not False:
            raise ValueError("every object schema must set additionalProperties: false")
        for child in value.values():
            if isinstance(child, dict):
                visit(child)
            elif isinstance(child, list):
                for element in child:
                    visit(element)

    visit(schema)


def _clean_environment() -> dict[str, str]:
    env = os.environ.copy()
    # An inherited API key could silently switch the CLI to billable API authentication.
    for key in list(env):
        upper = key.upper()
        if upper in {"OPENAI_API_KEY", "CODEX_API_KEY", "AZURE_OPENAI_API_KEY"}:
            del env[key]
    return env


def _digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class CodexProvider:
    """Use an existing ChatGPT Codex login for one bounded proposal call."""

    def __init__(self, model: str = "gpt-6-astra", cli_command: Sequence[str] | None = None):
        self.model = model
        self._command = list(cli_command) if cli_command is not None else _cli_command()
        if not self._command:
            raise ValueError("cli_command cannot be empty")

    def propose(
        self,
        prompt: str,
        schema: dict[str, Any],
        artifact_dir: Path,
        timeout_seconds: int = 180,
    ) -> dict[str, Any]:
        """Return a structured proposal and persist all local call evidence."""
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        if not isinstance(prompt, str) or not prompt.strip():
            raise ValueError("prompt must be nonempty")
        artifact_dir = Path(artifact_dir).resolve()
        artifact_dir.mkdir(parents=True, exist_ok=True)
        prompt_bytes = prompt.encode("utf-8")
        schema_bytes = json.dumps(schema, sort_keys=True, ensure_ascii=False, indent=2).encode(
            "utf-8"
        )
        (artifact_dir / "prompt.txt").write_bytes(prompt_bytes)
        (artifact_dir / "schema.json").write_bytes(schema_bytes)
        events_path = artifact_dir / "events.jsonl"
        output_path = artifact_dir / "output.json"
        events_path.write_bytes(b"")
        metadata: dict[str, Any] = {
            "status": "started",
            "requested_model": self.model,
            "auth_method": "unknown",
            "cli_version": "unknown",
            "prompt_sha256": _digest(prompt_bytes),
            "schema_sha256": _digest(schema_bytes),
            "output_sha256": None,
            "charge_usd": None,
            "usage": None,
            "elapsed_seconds": None,
            "timed_out": False,
            "event_log": str(events_path),
        }
        started = time.monotonic()
        env = _clean_environment()

        def remaining() -> float:
            left = timeout_seconds - (time.monotonic() - started)
            if left <= 0:
                raise TimeoutError("provider call timed out")
            return left

        def run(args: list[str], input_text: str | None = None) -> subprocess.CompletedProcess[str]:
            timeout = remaining()
            process = subprocess.Popen(
                self._command + args,
                stdin=subprocess.PIPE if input_text is not None else subprocess.DEVNULL,
                text=True,
                encoding="utf-8",
                errors="replace",
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                shell=False,
                env=env,
                cwd=artifact_dir,
                creationflags=(subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0),
                start_new_session=(os.name != "nt"),
            )
            try:
                stdout, stderr = process.communicate(input=input_text, timeout=timeout)
            except subprocess.TimeoutExpired as exc:
                metadata["timed_out"] = True
                if os.name == "nt" and process.poll() is None:
                    subprocess.run(
                        ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        timeout=10,
                        check=False,
                        shell=False,
                    )
                elif process.poll() is None:
                    os.killpg(process.pid, signal.SIGKILL)
                try:
                    stdout, stderr = process.communicate(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    stdout, stderr = process.communicate()
                (artifact_dir / "timeout-stdout.txt").write_text(stdout or "", encoding="utf-8")
                (artifact_dir / "timeout-stderr.txt").write_text(stderr or "", encoding="utf-8")
                raise TimeoutError(
                    "provider call timed out; owned process tree terminated"
                ) from exc
            return subprocess.CompletedProcess(
                self._command + args, process.returncode, stdout, stderr
            )

        try:
            _strict_schema(schema)
            version = run(["--version"])
            if version.returncode != 0:
                raise RuntimeError("Codex CLI version check failed")
            metadata["cli_version"] = version.stdout.strip()
            login = run(["login", "status"])
            if login.returncode != 0 or "Logged in using ChatGPT" not in (
                login.stdout + login.stderr
            ):
                raise RuntimeError("Codex CLI must be logged in using ChatGPT")
            metadata["auth_method"] = "ChatGPT"
            args = [
                "exec",
                "--ephemeral",
                "--sandbox",
                "read-only",
                "--skip-git-repo-check",
                "--ignore-user-config",
                "--model",
                self.model,
                "--disable",
                "shell_tool",
                "--disable",
                "apps",
                "--disable",
                "plugins",
                "--disable",
                "browser_use",
                "--disable",
                "computer_use",
                "--disable",
                "multi_agent",
                "--disable",
                "memories",
                "--disable",
                "view_image",
                "-c",
                'web_search="disabled"',
                "-c",
                'model_reasoning_effort="medium"',
                "--output-schema",
                str(artifact_dir / "schema.json"),
                "-o",
                str(output_path),
                "--json",
                "-",
            ]
            result = run(args, prompt)
            event_bytes = result.stdout.encode("utf-8")
            events_path.write_bytes(event_bytes)
            (artifact_dir / "stderr.txt").write_text(result.stderr, encoding="utf-8")
            metadata["exit_code"] = result.returncode
            if result.returncode != 0:
                raise RuntimeError(f"Codex CLI exited with status {result.returncode}")
            if not output_path.is_file():
                raise RuntimeError("Codex CLI did not produce structured output")
            output_bytes = output_path.read_bytes()
            metadata["output_sha256"] = _digest(output_bytes)
            proposal = json.loads(output_bytes)
            if not isinstance(proposal, dict):
                raise ValueError("structured output must be a JSON object")
            usage: dict[str, Any] | None = None
            completed = False
            for line in result.stdout.splitlines():
                if not line.strip():
                    continue
                event = json.loads(line)
                event_type = event.get("type")
                if isinstance(event_type, str) and event_type.startswith("item."):
                    item_type = event.get("item", {}).get("type")
                    if item_type not in {"agent_message", "reasoning", "error"}:
                        raise RuntimeError(f"unexpected Codex item type: {item_type}")
                elif event_type == "turn.completed":
                    completed = True
                    usage = event.get("usage")
            if not completed:
                raise RuntimeError("Codex event stream has no completed turn")
            metadata["status"] = "succeeded"
            metadata["usage"] = usage
            metadata["elapsed_seconds"] = time.monotonic() - started
            (artifact_dir / "metadata.json").write_text(
                json.dumps(metadata, indent=2, ensure_ascii=False), encoding="utf-8"
            )
            return {
                "proposal": proposal,
                "usage": usage,
                "elapsed_seconds": metadata["elapsed_seconds"],
                "requested_model": self.model,
                "cli_version": metadata["cli_version"],
                "auth_method": metadata["auth_method"],
                "event_log": events_path,
            }
        except (OSError, RuntimeError, ValueError, TimeoutError, subprocess.TimeoutExpired) as exc:
            if isinstance(exc, TimeoutError):
                metadata["timed_out"] = True
            metadata["status"] = "timed_out" if metadata["timed_out"] else "failed"
            metadata["elapsed_seconds"] = time.monotonic() - started
            metadata["error"] = f"{type(exc).__name__}: {exc}"
            (artifact_dir / "failure.json").write_text(
                json.dumps(metadata, indent=2, ensure_ascii=False), encoding="utf-8"
            )
            raise ProviderError(str(exc), artifact_dir) from exc
