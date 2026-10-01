import json, time
from pathlib import Path
from pandas.testing import assert_frame_equal
from frontier.research_lab import _read_history, _read_histories

if __name__ == "__main__":
    root=Path.cwd()
    state=json.loads((root/"artifacts/research-lab/status.json").read_text("utf-8"))
    records=json.loads((root/"artifacts/research-lab/runs"/state["run_id"]/"capture-index.json").read_text("utf-8"))[:100]
    started=time.perf_counter()
    observed=[]
    frames=_read_histories(root,records,lambda **value: observed.append(value))
    elapsed=time.perf_counter()-started
    for i in (0,49,99):
        assert_frame_equal(frames[i], _read_history(root, records[i]), check_exact=True)
    result={"histories":len(frames),"rows":sum(len(f) for f in frames),"elapsed_seconds":round(elapsed,3),"serial_comparisons_exact":3,"progress":observed}
    (root/"artifacts/research-lab/normalization-check.json").write_text(json.dumps(result,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(result))
