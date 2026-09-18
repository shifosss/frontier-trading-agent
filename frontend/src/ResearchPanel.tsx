import { useEffect, useState } from "react";
import { ratio, readable } from "./format";
import {
  ProposalAttempt,
  SavedJson,
  type ResearchAttempt,
} from "./ResearchDisplay";
import type { Dataset } from "./types";

type Obj = Record<string, any>;
type Props = {
  datasets: Dataset[];
  runs: Obj[];
  datasetId: string;
  setDatasetId: (id: string) => void;
  optIn: boolean;
  setOptIn: (value: boolean) => void;
  busy: string;
  request: (path: string, body?: unknown) => Promise<any>;
  work: (name: string, fn: () => Promise<void>) => Promise<void>;
  notice: (message: string) => void;
  error: (message: string) => void;
  openStudy: (id: string) => Promise<void>;
};
const datasetEvidence = (value: Dataset | undefined) =>
  value?.mode === "synthetic_fixture"
    ? "Synthetic engineering fixture"
    : "Historical snapshot";
export default function ResearchPanel(props: Props) {
  const {
    datasets,
    runs,
    datasetId,
    setDatasetId,
    optIn,
    setOptIn,
    busy,
    request,
    work,
    notice,
    error,
    openStudy,
  } = props;
  const [campaigns, setCampaigns] = useState<Obj[]>([]);
  const [frozen, setFrozen] = useState<Obj[]>([]);
  const [observations, setObservations] = useState<Obj[]>([]);
  const [sourceStatus, setSourceStatus] = useState<Obj | null>(null);
  const [selectedCampaign, setSelectedCampaign] = useState("");
  const [selectedFrozen, setSelectedFrozen] = useState("");
  const [observationDataset, setObservationDataset] = useState("");
  const [freezeRun, setFreezeRun] = useState("");
  const [loading, setLoading] = useState(true);
  const dataset = datasets.find((d) => d.dataset_id === datasetId);
  const activeCampaign = campaigns.find(
    (c) => c.campaign_id === selectedCampaign,
  );
  const activeFrozen = frozen.find((f) => f.frozen_id === selectedFrozen);
  const eligibleRuns = runs.filter((r) => r.status === "COMPLETED");
  const frozenDataset = activeFrozen?.source_dataset;
  const instrumentIdentity = (manifest: Pick<Dataset, "instruments">) =>
    JSON.stringify(
      manifest.instruments
        .map((instrument) => [
          instrument.id,
          instrument.venue,
          instrument.currency,
          instrument.exposure_group,
        ])
        .sort((a, b) => JSON.stringify(a).localeCompare(JSON.stringify(b))),
    );
  const eligibleDatasets = frozenDataset
    ? datasets.filter(
        (candidate) =>
          candidate.dataset_id !== activeFrozen?.input_dataset_id &&
          candidate.interval === frozenDataset.interval &&
          instrumentIdentity(candidate) === instrumentIdentity(frozenDataset) &&
          Date.parse(candidate.start) === Date.parse(frozenDataset.start) &&
          Date.parse(candidate.end) > Date.parse(frozenDataset.end),
      )
    : [];
  async function load() {
    const [c, f, o] = await Promise.all([
      request("/model-campaigns"),
      request("/frozen"),
      request("/observations"),
    ]);
    setCampaigns(c);
    setFrozen(f);
    setObservations(o);
    setSelectedCampaign((old) =>
      c.some((v: Obj) => v.campaign_id === old)
        ? old
        : (c[0]?.campaign_id ?? ""),
    );
    setSelectedFrozen((old) =>
      f.some((v: Obj) => v.frozen_id === old) ? old : (f[0]?.frozen_id ?? ""),
    );
  }
  useEffect(() => {
    let mounted = true;
    load()
      .catch((e) => {
        if (mounted) error(e.message);
      })
      .finally(() => {
        if (mounted) setLoading(false);
      });
    request("/sources/status")
      .then((value) => {
        if (mounted) setSourceStatus(value);
      })
      .catch((e) => {
        if (mounted) setSourceStatus({ error: e.message });
      });
    return () => {
      mounted = false;
    };
  }, []);
  useEffect(() => {
    if (!eligibleRuns.some((r) => r.id === freezeRun))
      setFreezeRun(eligibleRuns[0]?.id ?? "");
  }, [runs]);
  useEffect(() => {
    setObservationDataset((old) =>
      eligibleDatasets.some((d) => d.dataset_id === old)
        ? old
        : (eligibleDatasets[0]?.dataset_id ?? ""),
    );
  }, [selectedFrozen, frozen, datasets]);
  async function explore() {
    await work("Exploring with Codex", async () => {
      const campaign = await request("/model-campaigns", {
        dataset_id: datasetId,
        allow_incomplete_actions: optIn,
        max_proposals: 2,
      });
      await load();
      setSelectedCampaign(campaign.campaign_id);
      if (campaign.status === "FAILED")
        throw Error(
          `Research stopped after ${campaign.call_count ?? campaign.attempts.length} attempt(s). ${campaign.attempts.find((a: Obj) => a.error)?.error ?? "Inspect the saved attempt for details."}`,
        );
      notice(
        `Research finished: ${campaign.accepted_run_ids.length} accepted replay(s) from ${campaign.call_count ?? campaign.attempts.length} attempt(s). All attempts are saved.`,
      );
    });
  }
  return (
    <div className="research-workspace">
      <section className="wide-sheet research-protocol">
        <div className="section-heading">
          <div>
            <h2>Bounded model research</h2>
            <p>Two proposal calls. Typed strategies. Actual replay feedback.</p>
          </div>
          <button
            className="secondary compact"
            disabled={!!busy || loading}
            onClick={() => work("Refreshing saved research", load)}
          >
            Refresh saved research
          </button>
        </div>
        <div className="research-setup">
          <div>
            <label>
              Research dataset
              <select
                value={datasetId}
                onChange={(e) => setDatasetId(e.target.value)}
              >
                {!datasets.length && (
                  <option value="">No dataset imported</option>
                )}
                {datasets.map((d) => (
                  <option key={d.dataset_id} value={d.dataset_id}>
                    {d.name}
                  </option>
                ))}
              </select>
            </label>
            {dataset && (
              <p className="research-dataset">
                <span className="badge synthetic">
                  {datasetEvidence(dataset)}
                </span>{" "}
                {dataset.interval === "1h" ? "Hourly" : "Daily"} bars,{" "}
                {dataset.start.slice(0, 10)} to {dataset.end.slice(0, 10)}
              </p>
            )}
            {dataset?.corporate_actions_status === "unknown" && (
              <label className="check warning">
                <input
                  type="checkbox"
                  checked={optIn}
                  onChange={(e) => setOptIn(e.target.checked)}
                />
                <span>
                  Allow exploratory raw-price research. Distributions may be
                  omitted; this is not total return.
                </span>
              </label>
            )}
            <button
              className="primary"
              disabled={
                !!busy ||
                !datasetId ||
                (dataset?.corporate_actions_status === "unknown" && !optIn)
              }
              onClick={explore}
            >
              {busy === "Exploring with Codex"
                ? "Exploring with Codex…"
                : "Explore with Codex"}
            </button>
          </div>
          <div className="research-contract">
            <p>
              Uses the existing Codex ChatGPT login and its usage allowance. At
              most two calls, including rejected proposals and repairs.
            </p>
            <p>
              The model selects parameters for the built-in trend or reversion
              rule. Accepted proposals run through the same replay engine; the
              next call receives the previous attempt’s feedback.
            </p>
            <p>
              Fixed funding: USD 10,000 + CAD 10,000. Commission: 1 native
              currency unit per order. Slippage: 5 bps.
            </p>
            <p className="boundary-note">
              Historical evaluation is exploratory and adaptively selected. No
              automatic promotion or proof of future performance.
            </p>
          </div>
        </div>
      </section>
      <section className="wide-sheet campaign-history">
        <div className="section-heading">
          <h2>
            Saved model campaigns{" "}
            <span className="count">{campaigns.length}</span>
          </h2>
          {campaigns.length > 0 && (
            <label>
              Campaign
              <select
                value={selectedCampaign}
                onChange={(e) => setSelectedCampaign(e.target.value)}
              >
                {campaigns.map((c) => (
                  <option key={c.campaign_id} value={c.campaign_id}>
                    {c.created_at.slice(0, 16).replace("T", " ")} /{" "}
                    {readable(c.status)} / {c.attempts.length} attempts
                  </option>
                ))}
              </select>
            </label>
          )}
        </div>
        {loading ? (
          <p className="empty-small">Loading saved research records…</p>
        ) : !activeCampaign ? (
          <p className="empty-small">
            No saved campaigns. Select a dataset above to begin a bounded
            exploration.
          </p>
        ) : (
          <div className="campaign-content">
            <div className="campaign-context">
              <span
                className={`badge ${activeCampaign.status === "FAILED" ? "failed" : ""}`}
              >
                {readable(activeCampaign.status)}
              </span>
              <span>
                {activeCampaign.call_count ?? activeCampaign.attempts.length} /{" "}
                {activeCampaign.max_proposals} calls used
              </span>
              <span>
                {activeCampaign.accepted_run_ids.length} accepted replays
              </span>
              <span>
                {datasets.find(
                  (d) => d.dataset_id === activeCampaign.dataset_id,
                )?.name ?? "Saved dataset"}
              </span>
            </div>
            <p className="evaluation-note">
              Exposed evaluation interval:{" "}
              {activeCampaign.evaluation_access.start.slice(0, 10)} to{" "}
              {activeCampaign.evaluation_access.end.slice(0, 10)}.{" "}
              {activeCampaign.evaluation_access.prior_overlaps.length} earlier
              overlapping access record(s).
            </p>
            {activeCampaign.attempts.map((attempt: ResearchAttempt) => (
              <ProposalAttempt
                key={attempt.number}
                attempt={attempt}
                busy={!!busy}
                onInspect={(id) => work("Opening study", () => openStudy(id))}
              />
            ))}
            <ul className="research-limitations">
              {activeCampaign.limitations.map((text: string) => (
                <li key={text}>{text}</li>
              ))}
            </ul>
            <SavedJson value={activeCampaign} />
          </div>
        )}
      </section>
      <section className="wide-sheet observation-workspace">
        <div className="section-heading">
          <div>
            <h2>Frozen configurations and observations</h2>
            <p>
              Keep a configuration fixed, then inspect signals from a distinct
              dataset version.
            </p>
          </div>
          <span className="badge">Observation only</span>
        </div>
        <p className="observation-boundary">
          Observations do not infer positions, broker orders, fills or
          performance. A prospective record may remain pending; historical
          records do not become prospective evidence.
        </p>
        <div className="observation-controls">
          <div>
            <h3>Freeze a completed study</h3>
            <label>
              Completed study
              <select
                value={freezeRun}
                onChange={(e) => setFreezeRun(e.target.value)}
              >
                {!eligibleRuns.length && (
                  <option value="">No completed studies</option>
                )}
                {eligibleRuns.map((r) => (
                  <option value={r.id} key={r.id}>
                    {r.config.strategy.name} /{" "}
                    {r.created_at.slice(0, 16).replace("T", " ")} /{" "}
                    {r.mode === "synthetic_fixture"
                      ? "Synthetic fixture"
                      : "Historical snapshot"}
                  </option>
                ))}
              </select>
            </label>
            <button
              className="secondary"
              disabled={!!busy || !freezeRun}
              onClick={() =>
                work("Freezing configuration", async () => {
                  const saved = await request("/frozen", { run_id: freezeRun });
                  await load();
                  setSelectedFrozen(saved.frozen_id);
                  notice(
                    "Configuration frozen for observation. No strategy was promoted.",
                  );
                })
              }
            >
              Freeze configuration
            </button>
            <p>
              The completed run and original dataset stay attached to the frozen
              configuration.
            </p>
          </div>
          <div>
            <h3>Record an observation</h3>
            <label>
              Frozen configuration
              <select
                value={selectedFrozen}
                onChange={(e) => setSelectedFrozen(e.target.value)}
              >
                {!frozen.length && (
                  <option value="">No frozen configurations</option>
                )}
                {frozen.map((f) => (
                  <option value={f.frozen_id} key={f.frozen_id}>
                    {f.config.strategy.name} /{" "}
                    {f.created_at.slice(0, 16).replace("T", " ")}
                  </option>
                ))}
              </select>
            </label>
            <label>
              New dataset version
              <select
                value={observationDataset}
                onChange={(e) => setObservationDataset(e.target.value)}
              >
                {!eligibleDatasets.length && (
                  <option value="">
                    Import a compatible history extension first
                  </option>
                )}
                {eligibleDatasets.map((d) => (
                  <option value={d.dataset_id} key={d.dataset_id}>
                    {d.name}
                  </option>
                ))}
              </select>
            </label>
            <p className="observation-compatibility">
              Choose a history extension with the same instruments, currencies,
              exposure groups, bar interval and start date, plus later
              observations. The server also verifies the complete event-time
              prefix.
            </p>
            <button
              className="primary"
              disabled={
                !!busy ||
                !selectedFrozen ||
                !observationDataset ||
                observationDataset === activeFrozen?.input_dataset_id
              }
              onClick={() =>
                work("Recording observation", async () => {
                  const saved = await request("/observations", {
                    frozen_id: selectedFrozen,
                    dataset_id: observationDataset,
                  });
                  await load();
                  notice(
                    `Observation saved: ${readable(saved.classification)}. Fill outcome: ${readable(saved.next_fill_outcome)}.`,
                  );
                })
              }
            >
              Record observation
            </button>
            {activeFrozen && <SavedJson value={activeFrozen} />}
          </div>
        </div>
        <div className="observation-history">
          <h3>
            Saved observation records{" "}
            <span className="count">{observations.length}</span>
          </h3>
          {!observations.length ? (
            <p className="empty-small">
              No observation records yet. Freeze a study, then import and select
              a distinct dataset version.
            </p>
          ) : (
            observations.map((record) => (
              <details
                className="observation-record"
                key={record.observation_id}
              >
                <summary>
                  <span>{readable(record.classification)}</span>
                  <span>{record.as_of.slice(0, 19).replace("T", " ")} UTC</span>
                  <span>Outcome: {readable(record.next_fill_outcome)}</span>
                </summary>
                <p>
                  Actions: {record.corporate_actions_status}; known events{" "}
                  {record.known_actions_present ? "present" : "not reported"}.
                  No execution outcome inferred.
                </p>
                <div className="table-scroll">
                  <table>
                    <thead>
                      <tr>
                        <th>Instrument</th>
                        <th>Input available (UTC)</th>
                        <th>Signal</th>
                        <th>Target weight</th>
                        <th>Next eligible opening (UTC)</th>
                        <th>Reason</th>
                      </tr>
                    </thead>
                    <tbody>
                      {record.inputs.map((input: Obj) => (
                        <tr key={input.instrument_id}>
                          <td>{input.instrument_id}</td>
                          <td>{input.available_at}</td>
                          <td>
                            {input.signal == null
                              ? "Not due"
                              : String(input.signal)}
                          </td>
                          <td>
                            {input.target_weight == null
                              ? "Not set"
                              : ratio(input.target_weight)}
                          </td>
                          <td>{input.next_eligible_open}</td>
                          <td>{input.reason}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                <ul>
                  {record.limitations.map((text: string) => (
                    <li key={text}>{text}</li>
                  ))}
                </ul>
                <SavedJson value={record} />
              </details>
            ))
          )}
        </div>
      </section>
      <section className="wide-sheet research-source-status">
        <h2>Source access</h2>
        {!sourceStatus ? (
          <p>Checking read-only connector status…</p>
        ) : sourceStatus.error ? (
          <p>Source status unavailable: {sourceStatus.error}</p>
        ) : (
          <>
            <p>
              Standalone Longbridge CLI:{" "}
              <strong>
                {readable(sourceStatus.longbridge?.status ?? "unknown")}
              </strong>
              . {sourceStatus.longbridge?.hint}
            </p>
            <dl>
              {Object.entries(sourceStatus.acquisition ?? {}).map(
                ([key, value]) => (
                  <div key={key}>
                    <dt>{readable(key)}</dt>
                    <dd>{String(value)}</dd>
                  </div>
                ),
              )}
            </dl>
          </>
        )}
      </section>
    </div>
  );
}
