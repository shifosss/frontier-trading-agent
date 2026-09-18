import { useCallback, useEffect, useRef, useState } from "react";
import { Table } from "./StudyDisplay";
import { number, percent, readable } from "./format";

type Props = {
  request: (path: string, body?: unknown) => Promise<any>;
  error: (message: string) => void;
};
type Status = {
  status:
    | "idle"
    | "starting"
    | "running"
    | "failed"
    | "interrupted"
    | "completed";
  phase?: string;
  message?: string;
  started_at?: string;
  updated_at?: string;
  discovered?: number;
  requested?: number;
  cached?: number;
  attempted?: number;
  usable?: number;
  failed?: number;
  latest?: { run_id: string; created_at: string } | null;
};
type Summary = {
  currency: string;
  strategy: string;
  horizon: number;
  budget: number;
  period: string;
  cost_bps: number;
  scheduled_cohorts: number;
  complete_cohorts: number;
  incomplete_cohorts: number;
  purged_cohorts: number;
  pending_cohorts: number;
  cash_only_cohorts: number;
  mean_return: number | null;
  mean_benchmark_return: number | null;
  mean_excess_return: number | null;
  mean_invested_fraction: number | null;
};
type Candidate = {
  currency: string;
  strategy: string;
  symbol: string;
  session: string;
  rank: number;
  price: number;
  average_dollar_volume_20: number;
  quantities_by_budget: Record<string, number>;
};
type Result = {
  run_id: string;
  created_at: string;
  capture: {
    discovered: number;
    requested: number;
    usable: number;
    rows: number;
    failed: unknown[];
  };
  forward_observation?: {
    status: string;
    planned_cohorts: number;
    tracked_cohorts: number;
    pending_count: number;
    complete_count: number;
    incomplete_count: number;
    version_mismatch_count: number;
    snapshot_recorded_at: string;
    evaluation_path?: string;
  };
  summaries: Summary[];
  latest_candidates: Candidate[];
  methodology: {
    kind: string;
    entry: string;
    sizing: string;
    costs: string;
    benchmark: string;
    partition: string;
    missing_data: string;
    budgets: number[];
    periods: Record<
      string,
      Record<
        string,
        { first_session: string | null; last_session: string | null }
      >
    >;
    limitations: string[];
  };
};
const strategies = [
  [
    "momentum",
    "Momentum",
    "Positive medium-term momentum above the 50-day mean.",
  ],
  [
    "trend_pullback",
    "Trend pullback",
    "A short pullback within a longer upward trend.",
  ],
  [
    "mean_reversion",
    "Mean reversion",
    "An unusually weak close within a longer upward trend.",
  ],
  [
    "breakout",
    "Breakout",
    "A close reaching the preceding 55 sessions’ highest closing price.",
  ],
] as const;
const statuses: Record<Status["status"], string> = {
  idle: "Ready to start",
  starting: "Starting research worker",
  running: "Research is running",
  failed: "Research needs attention",
  interrupted: "Research was interrupted",
  completed: "Research completed",
};
const count = (value?: number) =>
  value === undefined ? "—" : number(value, 0);
const rate = (value?: number | null) =>
  value == null ? "Insufficient observations" : percent(value);
const timestamp = (value?: string) =>
  value ? new Date(value).toLocaleString("en-CA") : "Not started";

export default function BroadResearchPanel({ request, error }: Props) {
  const [state, setState] = useState<Status | null>(null);
  const [result, setResult] = useState<Result | null>(null);
  const [loading, setLoading] = useState(false);
  const [starting, setStarting] = useState(false);
  const [currency, setCurrency] = useState("USD");
  const [budget, setBudget] = useState(500);
  const [period, setPeriod] = useState("evaluation");
  const [horizon, setHorizon] = useState(10);
  const [cost, setCost] = useState(40);
  const [candidateFamily, setCandidateFamily] = useState("momentum");
  const [affordableOnly, setAffordableOnly] = useState(true);
  const loadedRun = useRef("");
  const active = state?.status === "running" || state?.status === "starting";
  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const next: Status = await request("/research-lab/status");
      setState(next);
      if (next.latest && loadedRun.current !== next.latest.run_id) {
        const saved: Result = await request(
          `/research-lab/runs/${next.latest.run_id}`,
        );
        setResult(saved);
        loadedRun.current = saved.run_id;
      }
    } catch (failure) {
      error((failure as Error).message);
    } finally {
      setLoading(false);
    }
  }, [request, error]);
  useEffect(() => {
    void refresh();
  }, [refresh]);
  useEffect(() => {
    if (!active) return;
    const timer = window.setInterval(() => {
      void refresh();
    }, 5000);
    return () => window.clearInterval(timer);
  }, [active, refresh]);
  async function start() {
    setStarting(true);
    error("");
    try {
      const next: Status = await request("/research-lab/start", {});
      setState(next);
    } catch (failure) {
      error((failure as Error).message);
    } finally {
      setStarting(false);
    }
  }
  const comparisons =
    result?.summaries.filter(
      (row) =>
        row.currency === currency &&
        row.budget === budget &&
        row.period === period &&
        row.horizon === horizon &&
        row.cost_bps === cost,
    ) ?? [];
  const currentCandidates =
    result?.latest_candidates.filter(
      (row) => row.currency === currency && row.strategy === candidateFamily,
    ) ?? [];
  const shownCandidates = currentCandidates.filter(
    (row) =>
      !affordableOnly || (row.quantities_by_budget[String(budget)] ?? 0) > 0,
  );
  const shortlisted = new Set(
    currentCandidates
      .filter((row) => (row.quantities_by_budget[String(budget)] ?? 0) > 0)
      .slice(0, 5)
      .map((row) => row.symbol),
  );
  const dates = result?.methodology.periods[currency]?.[period];
  const requested = state?.requested ?? 0;
  const captured = (state?.cached ?? 0) + (state?.attempted ?? 0);
  return (
    <div className="broad-research">
      <section className="wide-sheet">
        <div className="section-heading">
          <div>
            <h2>A broader search for useful strategies</h2>
            <p>
              US and Canadian stocks · four fixed strategy families ·
              independent research
            </p>
          </div>
          <div className="lab-actions">
            <button
              className="secondary compact"
              disabled={loading}
              onClick={() => void refresh()}
            >
              {loading ? "Loading status…" : "Refresh status"}
            </button>
            <button
              className="primary compact"
              disabled={active || starting || state === null}
              onClick={() => void start()}
            >
              {starting || active
                ? "Research running"
                : state?.status === "failed" || state?.status === "interrupted"
                  ? "Resume broad research"
                  : "Run broad research"}
            </button>
          </div>
        </div>
        <div
          className={`operator-state ${state?.status === "failed" || state?.status === "interrupted" ? "operator-attention" : ""}`}
          role="status"
          aria-live="polite"
        >
          <span className="badge synthetic">Research only</span>
          <h3>{state ? statuses[state.status] : "Loading research status"}</h3>
          <p>
            {state?.message ??
              (active
                ? `Phase: ${readable(state?.phase)}.`
                : "Start a broad study or inspect the latest saved evidence below.")}
          </p>
          {active && requested > 0 && (
            <progress
              className="lab-progress"
              value={Math.min(captured, requested)}
              max={requested}
              aria-label="Market history capture progress"
            />
          )}
          <p className="lab-timestamp">
            Last update: {timestamp(state?.updated_at)}
            {active && " · Status refreshes every five seconds."}
          </p>
        </div>
        <div className="lab-counters" aria-label="Research progress">
          {(
            [
              ["Discovered", state?.discovered],
              ["Requested", state?.requested],
              ["Already cached", state?.cached],
              ["New attempts", state?.attempted],
              ["Usable histories", state?.usable],
              ["Capture failures", state?.failed],
            ] as const
          ).map(([label, value]) => (
            <div key={label}>
              <span>{label}</span>
              <strong>{count(value)}</strong>
            </div>
          ))}
        </div>
        <p className="operator-copy">
          This lab discovers exchange listings and resumes saved price
          downloads. The starter scanner uses 41 instruments. The running paper
          policy remains pinned to its original 11 US stocks; research results
          never change its orders automatically.
        </p>
      </section>
      <section className="lab-families" aria-label="Strategy families">
        {strategies.map(([key, title, description]) => (
          <article key={key}>
            <h3>{title}</h3>
            <p>{description}</p>
          </article>
        ))}
      </section>
      {!result ? (
        <section className="wide-sheet lab-empty">
          <h2>
            {active
              ? "Collecting the evidence"
              : "No completed broad study yet"}
          </h2>
          <p>
            The study compares 5, 10 and 20-session holding periods; 500, 2,000,
            10,000 and 100,000 in each currency; and three trading-cost
            scenarios. Results appear here after evaluation.
          </p>
          <p>
            Each forward cohort starts with fresh simulated cash. Its return is
            a diagnostic observation, not a continuous account return or
            evidence of a profitable live strategy.
          </p>
        </section>
      ) : (
        <>
          <section className="wide-sheet">
            <div className="section-heading">
              <div>
                <h2>Latest completed comparison</h2>
                <p>
                  {timestamp(result.created_at)} ·{" "}
                  {count(result.capture.usable)} usable histories ·{" "}
                  {count(result.capture.rows)} daily observations
                  {active && " · Previous completed run"}
                </p>
              </div>
              <a
                className="text-button"
                href={`/api/research-lab/runs/${result.run_id}/download`}
                download
              >
                Download full evidence
              </a>
            </div>
            <p className="operator-copy lab-evidence">
              Cash-weighted forward cohorts, not an account backtest. Current
              listing membership and revised historical prices introduce
              selection and survivorship bias. All four families are shown; this
              comparison does not select a strategy for the paper account.
            </p>
            <div className="lab-filters">
              <label>
                Market currency
                <select
                  aria-label="Market currency"
                  value={currency}
                  onChange={(e) => setCurrency(e.target.value)}
                >
                  <option>USD</option>
                  <option>CAD</option>
                </select>
              </label>
              <label>
                Simulated budget
                <select
                  aria-label="Simulated budget"
                  value={budget}
                  onChange={(e) => setBudget(Number(e.target.value))}
                >
                  {result.methodology.budgets.map((value) => (
                    <option key={value} value={value}>
                      {number(value, 0)} {currency}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                Chronological period
                <select
                  aria-label="Chronological period"
                  value={period}
                  onChange={(e) => setPeriod(e.target.value)}
                >
                  <option value="development">Development</option>
                  <option value="validation">Validation</option>
                  <option value="evaluation">Evaluation</option>
                </select>
              </label>
              <label>
                Holding period
                <select
                  aria-label="Holding period"
                  value={horizon}
                  onChange={(e) => setHorizon(Number(e.target.value))}
                >
                  {[5, 10, 20].map((value) => (
                    <option key={value} value={value}>
                      {value} sessions
                    </option>
                  ))}
                </select>
              </label>
              <label>
                Round-trip costs
                <select
                  aria-label="Round-trip costs"
                  value={cost}
                  onChange={(e) => setCost(Number(e.target.value))}
                >
                  {[20, 40, 100].map((value) => (
                    <option key={value} value={value}>
                      {value} bps
                    </option>
                  ))}
                </select>
              </label>
            </div>
            <p className="operator-copy">
              {dates?.first_session
                ? `${dates.first_session} to ${dates.last_session}. `
                : "No period data. "}
              Returns use the full cash budget, including uninvested cash.
              Benchmark: {currency === "USD" ? "SPY" : "XIU.TO"}. Changing the
              budget changes whole-share affordability. It does not change your
              paper balance.
            </p>
            <Table
              rows={strategies.map(([key, title]) => {
                const row = comparisons.find((item) => item.strategy === key);
                return {
                  family: title,
                  mean: rate(row?.mean_return),
                  benchmark: rate(row?.mean_benchmark_return),
                  excess: rate(row?.mean_excess_return),
                  invested: rate(row?.mean_invested_fraction),
                  complete: count(row?.complete_cohorts),
                  incomplete: count(row?.incomplete_cohorts),
                  pending: count(row?.pending_cohorts),
                  purged: count(row?.purged_cohorts),
                  cash: count(row?.cash_only_cohorts),
                };
              })}
              columns={[
                ["family", "Family"],
                ["mean", "Mean cohort return"],
                ["benchmark", "Benchmark mean"],
                ["excess", "Mean excess"],
                ["invested", "Mean invested"],
                ["complete", "Complete cohorts"],
                ["incomplete", "Missing data"],
                ["pending", "Not yet mature"],
                ["purged", "Boundary excluded"],
                ["cash", "Cash only"],
              ]}
            />
          </section>
          {result.forward_observation && (
            <section className="wide-sheet">
              <div className="section-heading">
                <div>
                  <h2>Forward observations</h2>
                  <p>
                    {readable(result.forward_observation.status)} · Recorded{" "}
                    {timestamp(result.forward_observation.snapshot_recorded_at)}
                  </p>
                </div>
                {result.forward_observation.evaluation_path && (
                  <a
                    className="text-button"
                    href={`/api/research-lab/runs/${result.run_id}/forward`}
                    download
                  >
                    Download forward observations
                  </a>
                )}
              </div>
              <div className="lab-counters">
                {(
                  [
                    [
                      "Snapshot plans",
                      result.forward_observation.planned_cohorts,
                    ],
                    [
                      "Tracked cohorts",
                      result.forward_observation.tracked_cohorts,
                    ],
                    [
                      "Awaiting outcomes",
                      result.forward_observation.pending_count,
                    ],
                    ["Complete", result.forward_observation.complete_count],
                    [
                      "Missing data",
                      result.forward_observation.incomplete_count,
                    ],
                    [
                      "Blocked by version",
                      result.forward_observation.version_mismatch_count,
                    ],
                  ] as const
                ).map(([label, value]) => (
                  <div key={label}>
                    <span>{label}</span>
                    <strong>{count(value)}</strong>
                  </div>
                ))}
              </div>
              <p className="operator-copy">
                Signals are frozen before future entry sessions. Outcomes become
                measurable as later prices arrive. These prospective research
                observations are separate from broker orders.
              </p>
            </section>
          )}
          <section className="wide-sheet">
            <div className="section-heading">
              <div>
                <h2>Latest research candidates</h2>
                <p>
                  Ranked from the latest completed session. These are research
                  observations, not orders.
                </p>
              </div>
            </div>
            <div className="lab-candidate-controls">
              <label>
                Strategy family
                <select
                  aria-label="Strategy family"
                  value={candidateFamily}
                  onChange={(e) => setCandidateFamily(e.target.value)}
                >
                  {strategies.map(([key, title]) => (
                    <option key={key} value={key}>
                      {title}
                    </option>
                  ))}
                </select>
              </label>
              <label className="check">
                <input
                  type="checkbox"
                  checked={affordableOnly}
                  onChange={(e) => setAffordableOnly(e.target.checked)}
                />{" "}
                Affordable at {number(budget, 0)} {currency}
              </label>
            </div>
            <p className="operator-copy">
              Showing {Math.min(25, shownCandidates.length)} of{" "}
              {count(shownCandidates.length)}
              {affordableOnly ? " affordable" : " ranked"} candidates in this
              family and currency. Only the first five affordable names form
              each study basket. Other quantities show per-name capacity, not a
              portfolio of all rows. Period, horizon and cost filters above
              apply to historical comparisons; current candidates use the
              selected currency and budget.
            </p>
            {shownCandidates.length ? (
              <Table
                rows={shownCandidates.slice(0, 25).map((row) => ({
                  symbol: row.symbol,
                  session: row.session,
                  rank: String(row.rank),
                  price: number(row.price),
                  volume: number(row.average_dollar_volume_20, 0),
                  quantity: String(
                    row.quantities_by_budget[String(budget)] ?? 0,
                  ),
                  shortlist: shortlisted.has(row.symbol)
                    ? "First five affordable"
                    : (row.quantities_by_budget[String(budget)] ?? 0) > 0
                      ? "Beyond first five"
                      : "Not affordable",
                }))}
                columns={[
                  ["symbol", "Symbol"],
                  ["session", "Source session"],
                  ["rank", "Family rank"],
                  ["price", `Close · ${currency}`],
                  ["volume", `20-day traded value · ${currency}`],
                  ["quantity", "Per-name shares"],
                  ["shortlist", "Research shortlist"],
                ]}
              />
            ) : (
              <p className="empty-small">
                No {affordableOnly ? "affordable " : ""}candidates meet this
                family’s current rules.
              </p>
            )}
          </section>
          <section className="wide-sheet lab-methodology">
            <details>
              <summary>Method and limitations</summary>
              <dl>
                {(
                  [
                    ["Entry and exit", result.methodology.entry],
                    ["Position sizing", result.methodology.sizing],
                    ["Costs", result.methodology.costs],
                    ["Benchmark", result.methodology.benchmark],
                    ["Chronological partitions", result.methodology.partition],
                    ["Missing observations", result.methodology.missing_data],
                  ] as const
                ).map(([title, text]) => (
                  <div key={title}>
                    <dt>{title}</dt>
                    <dd>{text}</dd>
                  </div>
                ))}
              </dl>
              <ul>
                {result.methodology.limitations.map((item) => (
                  <li key={item}>{item}</li>
                ))}
              </ul>
            </details>
          </section>
        </>
      )}
    </div>
  );
}
