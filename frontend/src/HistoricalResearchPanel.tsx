import { useCallback, useEffect, useRef, useState } from "react";
import { EquityChart, Table } from "./StudyDisplay";
import { number, percent, readable } from "./format";

type Props = {
  request: (path: string, body?: unknown) => Promise<any>;
  error: (message: string) => void;
};
type Portfolio = {
  currency: string;
  budget: number;
  cost_bps: number;
  strategy?: string;
  horizon?: number;
  status: string;
  missing?: string[];
  total_return: number | null;
  max_drawdown: number | null;
  cagr: number | null;
  ending_equity: number | null;
  trades: number;
  fees: number;
  first_session: string;
  last_session: string;
  monthly_equity_curve?: {
    session: string;
    equity: number | null;
    cash: number | null;
  }[];
  benchmark?: Portfolio;
  folds?: {
    training_start: string;
    training_end: string;
    test_start: string;
    test_end: string;
    selected_strategy: string;
    selected_horizon: number;
    test_return: number | null;
  }[];
};
type Result = {
  run_id: string;
  created_at: string;
  capture: {
    discovered: number;
    usable: number;
    rows: number;
    failed: unknown[];
    markets: {
      currency: string;
      first_session: string;
      last_session: string;
      rows: number;
    }[];
  };
  methodology: { limitations: string[]; attempts: unknown[] };
  portfolios: Portfolio[];
  benchmarks: (Portfolio & { symbol: string })[];
  walk_forward: Portfolio[];
};
type Status = {
  status: string;
  phase?: string;
  message?: string;
  currency?: string;
  requested?: number;
  cached?: number;
  attempted?: number;
  usable?: number;
  failed?: number;
  normalized?: number;
  market_histories?: number;
  updated_at?: string;
  latest?: { run_id: string };
};
const rate = (value: number | null | undefined) =>
  value == null ? "Unavailable" : percent(value);

export default function HistoricalResearchPanel({ request, error }: Props) {
  const [state, setState] = useState<Status>({ status: "loading" });
  const [result, setResult] = useState<Result | null>(null);
  const [currency, setCurrency] = useState("USD");
  const [budget, setBudget] = useState(500);
  const [cost, setCost] = useState(40);
  const [busy, setBusy] = useState(false);
  const loaded = useRef("");
  const active = state.status === "running" || state.status === "starting";
  const refresh = useCallback(async () => {
    try {
      const next: Status = await request("/historical-lab/status");
      setState(next);
      if (next.latest && loaded.current !== next.latest.run_id) {
        const report = await request(
          `/historical-lab/runs/${next.latest.run_id}`,
        );
        setResult(report);
        loaded.current = report.run_id;
      }
    } catch (failure) {
      error((failure as Error).message);
    }
  }, [request, error]);
  useEffect(() => {
    void refresh();
  }, [refresh]);
  useEffect(() => {
    if (!active) return;
    const timer = window.setInterval(() => void refresh(), 5000);
    return () => window.clearInterval(timer);
  }, [active, refresh]);
  async function start() {
    setBusy(true);
    try {
      setState(await request("/historical-lab/start", {}));
    } catch (failure) {
      error((failure as Error).message);
    } finally {
      setBusy(false);
    }
  }
  const matches = (row: Portfolio) =>
    row.currency === currency && row.budget === budget && row.cost_bps === cost;
  const rows = [
    ...(result?.portfolios.filter(matches) ?? []),
    ...(result?.benchmarks
      .filter(matches)
      .map((r) => ({ ...r, strategy: `${r.symbol} buy and hold` })) ?? []),
  ];
  const walk = result?.walk_forward.find(matches);
  const compareBenchmark =
    walk?.status === "complete" &&
    walk.benchmark?.status === "complete" &&
    walk.first_session === walk.benchmark.first_session &&
    walk.last_session === walk.benchmark.last_session;
  const chartSeries = walk
    ? [
        {
          name:
            walk.status === "complete"
              ? "Rolling selection"
              : "Rolling selection (partial history)",
          color: "#78d7bb",
          points: (walk.monthly_equity_curve ?? [])
            .filter((point) => point.equity != null)
            .map((point) => ({ timestamp: point.session, nav: point.equity! })),
        },
        ...(compareBenchmark
          ? [
              {
                name: "Buy and hold benchmark",
                color: "#caa574",
                points: (walk.benchmark?.monthly_equity_curve ?? [])
                  .filter((point) => point.equity != null)
                  .map((point) => ({
                    timestamp: point.session,
                    nav: point.equity!,
                  })),
              },
            ]
          : []),
      ]
    : [];
  return (
    <section className="wide-sheet historical-research">
      <div className="section-heading">
        <div>
          <h2>Historical strategy development</h2>
          <p>
            History from 2000 where available · continuous cash portfolios ·
            rolling annual tests
          </p>
        </div>
        <div className="lab-actions">
          <button className="secondary compact" onClick={() => void refresh()}>
            Refresh historical status
          </button>
          <button
            className="primary compact"
            disabled={active || busy || state.status === "loading"}
            onClick={() => void start()}
          >
            {active || busy
              ? "Historical study running"
              : "Run / resume historical study"}
          </button>
        </div>
      </div>
      <div role="status" aria-live="polite" className="operator-state">
        <span className="badge synthetic">Historical research</span>
        <h3>
          {readable(state.status)}
          {state.phase ? ` · ${readable(state.phase)}` : ""}
        </h3>
        <p>
          {state.message ??
            "Long histories support repeated tests before new forward observations mature."}
        </p>
        {state.requested != null && (
          <p>
            {number(state.usable ?? state.cached ?? 0, 0)} usable histories ·{" "}
            {number(state.requested, 0)} requested ·{" "}
            {number(state.failed ?? 0, 0)} capture failures
          </p>
        )}
        {active && state.phase === "capture" && !!state.requested && (
          <progress
            className="lab-progress"
            aria-label="Long historical capture progress"
            max={state.requested}
            value={(state.cached ?? 0) + (state.attempted ?? 0)}
          />
        )}
        {active && state.phase === "normalization" && (
          <p>
            {state.currency}: {number(state.normalized ?? 0, 0)} /{" "}
            {number(state.market_histories ?? 0, 0)} histories prepared
          </p>
        )}
      </div>
      {result && (
        <>
          <p>
            {number(result.capture.usable, 0)} histories ·{" "}
            {number(result.capture.rows, 0)} daily observations ·{" "}
            {number(result.methodology.attempts.length, 0)} declared strategy
            variants.
            {result.capture.markets.map(
              (m) => ` ${m.currency}: ${m.first_session} to ${m.last_session}.`,
            )}
          </p>
          <div className="lab-actions">
            <label>
              Historical currency{" "}
              <select
                value={currency}
                onChange={(e) => setCurrency(e.target.value)}
              >
                <option>USD</option>
                <option>CAD</option>
              </select>
            </label>
            <label>
              Historical starting cash{" "}
              <select
                value={budget}
                onChange={(e) => setBudget(Number(e.target.value))}
              >
                {[500, 2000, 10000, 100000].map((v) => (
                  <option key={v} value={v}>
                    {number(v, 0)}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Historical round-trip cost{" "}
              <select
                value={cost}
                onChange={(e) => setCost(Number(e.target.value))}
              >
                {[20, 40, 100].map((v) => (
                  <option key={v} value={v}>
                    {v} bps
                  </option>
                ))}
              </select>
            </label>
            <a
              className="button secondary compact"
              href={`/api/historical-lab/runs/${result.run_id}/download`}
            >
              Download historical evidence
            </a>
          </div>
          <h3>Training-only selection, tested on the following year</h3>
          <p>
            Each selection uses the previous three years. Test periods keep
            their selected rule; cash remains an eligible choice. These are
            retrospective tests designed today, with current listing and data
            limitations.
          </p>
          {walk ? (
            <>
              {walk.status !== "complete" && (
                <div className="operator-state" role="note">
                  <strong>{readable(walk.status)} historical test</strong>
                  <p>
                    {walk.status === "incomplete"
                      ? "This test stopped because required historical observations are missing. Any curve below shows only the available partial history."
                      : "There is not enough history to complete this rolling test."}{" "}
                    Full-period returns, drawdowns, and benchmark comparisons
                    are unavailable.
                  </p>
                  {!!walk.missing?.length && (
                    <ul aria-label="Missing historical observations">
                      {walk.missing.map((item) => (
                        <li key={item}>{item.replaceAll(":", " · ")}</li>
                      ))}
                    </ul>
                  )}
                </div>
              )}
              {chartSeries.some((series) => series.points.length > 0) ? (
                <div
                  className="historical-chart-scroll"
                  role="region"
                  aria-label="Scrollable historical equity chart"
                  tabIndex={0}
                >
                  <EquityChart currency={currency} series={chartSeries} />
                </div>
              ) : (
                <p>No usable equity path is available for this test.</p>
              )}
              <p>
                Chart samples month-end equity; completed-test drawdowns use
                daily marks.
                {compareBenchmark
                  ? " Benchmark covers the same completed test period."
                  : ""}
              </p>
              <p>
                <strong>{readable(walk.status)}</strong> · total return{" "}
                {rate(walk.total_return)} · maximum drawdown{" "}
                {rate(walk.max_drawdown)} · annualized return {rate(walk.cagr)}{" "}
                · {number(walk.trades, 0)} trades
              </p>
              {compareBenchmark && (
                <p>
                  Same-period benchmark return:{" "}
                  {rate(walk.benchmark?.total_return)} · drawdown:{" "}
                  {rate(walk.benchmark?.max_drawdown)}.
                </p>
              )}
              {(walk.max_drawdown ?? 0) > 0.3 && (
                <p>This test exceeds your 30% maximum loss tolerance.</p>
              )}
              <Table
                columns={[
                  ["training", "Training interval"],
                  ["test", "Test interval"],
                  ["rule", "Chosen rule"],
                  ["hold", "Hold"],
                  ["result", "Test return"],
                ]}
                rows={(walk.folds ?? []).map((f) => ({
                  training: `${f.training_start} – ${f.training_end}`,
                  test: `${f.test_start} – ${f.test_end}`,
                  rule: readable(f.selected_strategy),
                  hold:
                    f.selected_strategy === "cash"
                      ? "Cash"
                      : `${f.selected_horizon} sessions`,
                  result: rate(f.test_return),
                }))}
              />
            </>
          ) : (
            <p>No rolling test is available for this selection.</p>
          )}
          <h3>All fixed strategies and benchmarks</h3>
          <p>
            Whole-period results are exploratory comparisons. Starting cash
            stays in the account between trades; unused cash earns zero. Returns
            exclude contributions, taxes and FX.
          </p>
          <Table
            columns={[
              ["rule", "Rule"],
              ["hold", "Hold"],
              ["status", "Status"],
              ["total", "Total return"],
              ["drawdown", "Max drawdown"],
              ["annual", "Annualized"],
              ["trades", "Trades"],
              ["fees", "Fees"],
            ]}
            rows={rows.map((r) => ({
              rule: readable(r.strategy),
              hold: r.horizon ? `${r.horizon} sessions` : "—",
              status: readable(r.status),
              total: rate(r.total_return),
              drawdown: rate(r.max_drawdown),
              annual: rate(r.cagr),
              trades: number(r.trades, 0),
              fees: number(r.fees, 2),
            }))}
          />
          <details>
            <summary>Data and simulation limitations</summary>
            <ul>
              {result.methodology.limitations.map((item) => (
                <li key={item}>{item}</li>
              ))}
            </ul>
          </details>
        </>
      )}
    </section>
  );
}
