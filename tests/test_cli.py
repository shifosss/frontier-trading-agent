import json

from typer.testing import CliRunner

from frontier.cli import app


def test_cli_demo_inspection_and_identical_replay(tmp_path):
    runner = CliRunner()
    workspace = ["--workspace", str(tmp_path)]
    demo = runner.invoke(app, workspace + ["demo"])
    assert demo.exit_code == 0, demo.output
    record = json.loads(demo.stdout)
    assert record["status"] == "COMPLETED"
    show = runner.invoke(app, workspace + ["show", record["id"]])
    envelope = json.loads(show.stdout)
    assert envelope["result"]["summary"]["trade_count"] > 0
    verify = runner.invoke(app, workspace + ["verify-replay", record["id"]])
    assert verify.exit_code == 0, verify.output
    assert json.loads(verify.stdout)["identical"]
    assert runner.invoke(app, workspace + ["doctor"]).exit_code == 0
    assert runner.invoke(app, workspace + ["datasets"]).exit_code == 0
    assert runner.invoke(app, workspace + ["runs"]).exit_code == 0
