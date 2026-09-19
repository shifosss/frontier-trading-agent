import { useCallback, useEffect, useRef, useState } from "react";
import { EquityChart, Table } from "./StudyDisplay";
import { number, percent, readable } from "./format";

type Props = {
  request: (path: string, body?: unknown) => Promise<any>;
  error: (message: string) => void;
};
type TradeMetrics = {
  completed_trades: number;
  net_expectancy_native?: number | null;
  net_expectancy_return?: number | null;
  win_rate?: number | null;
  annualized_turnover?: number | null;
  mean_exposure_fraction?: number | null;
  mean_holding_sessions?: number | null;
  mean_holding_calendar_days?: number | null;
  trades_per_week?: number | null;
};
type PeriodMetrics = {
  count: number;
  profitable_fraction: number | null;
  mean_return: number | null;
  median_return: number | null;
  worst_return: number | null;
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
  trade_metrics?: TradeMetrics;
  period_metrics?: { weekly?: PeriodMetrics; monthly?: PeriodMetrics };
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
type ModelDiagnostic = {
  currency: string;
  training_start: string;
  training_end: string;
  calibration_start: string;
  calibration_end: string;
  test_start: string;
  test_end: string;
  fit_rows: number;
  calibration_rows: number;
  prediction_rows: number;
  excluded_label_rows: number;
  calibration?: {
    baseline_mse?: number[];
    model_mse?: Record<string, number[]>;
    horizons?: Record<
      string,
      {
        weights: Record<string, number>;
        equal_weight_fallback: boolean;
      }
    >;
  };
  warnings?: string[];
};
type ForecastCandidate = {
  currency: string;
  strategy: string;
  horizon: number;
  symbol: string;
  session: string;
  predicted_return: number;
  predicted_downside: number;
  score_40bps: number;
  rank: number;
  price: number;
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
  study_mode?: string;
  methodology: {
    version?: string;
    horizons?: number[];
    budgets?: number[];
    cost_bps?: number[];
    screening_frequency?: string;
    execution?: string;
    limitations: string[];
    attempts: unknown[];
  };
  portfolios: Portfolio[];
  benchmarks: (Portfolio & { symbol: string })[];
  walk_forward: Portfolio[];
  model_diagnostics?: ModelDiagnostic[];
  latest_candidates?: ForecastCandidate[];
};
type Status = {
  status: string;
  run_id?: string;
  study_mode?: string;
  phase?: string;
  stage?: string;
  budget?: number;
  test_start?: string;
  symbols?: number;
  fold?: number;
  total_folds?: number;
  model?: string;
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
const amount = (value: number | null | undefined, decimals = 2) =>
  value == null ? "Unavailable" : number(value, decimals);
const completedValue = (row: Portfolio, value: number | null | undefined) =>
  row.status === "complete" ? value : null;
const portfolioKey = (row: Portfolio) => `${row.strategy}:${row.horizon}`;

function ModelDiagnostics({ rows }: { rows: ModelDiagnostic[] }) {
  return (
    <details>
      <summary>
        Model refits and calibration · {number(rows.length, 0)} test windows
      </summary>
      <p>
        Fitting, calibration and testing use separate chronological intervals.
        Error diagnostics measure forecasts; they do not establish trading
        profit. Equal-weight fallbacks are shown explicitly.
      </p>
      <Table
        columns={[
          ["fit", "Fit interval"],
          ["calibration", "Calibration interval"],
          ["test", "Test interval"],
          ["fit_rows", "Fit rows"],
          ["calibration_rows", "Calibration rows"],
          ["predictions", "Prediction rows"],
          ["excluded", "Excluded labels"],
          ["weights", "Calibration weights by hold"],
          ["baseline", "Baseline MSE (return / downside)"],
          ["model_error", "Model MSE (return / downside)"],
          ["warnings", "Warnings"],
        ]}
        rows={rows.map((row) => ({
          fit: `${row.training_start} – ${row.training_end}`,
          calibration: `${row.calibration_start} – ${row.calibration_end}`,
          test: `${row.test_start} – ${row.test_end}`,
          fit_rows: number(row.fit_rows, 0),
          calibration_rows: number(row.calibration_rows, 0),
          predictions: number(row.prediction_rows, 0),
          excluded: number(row.excluded_label_rows, 0),
          weights:
            Object.entries(row.calibration?.horizons ?? {})
              .map(
                ([hold, value]) =>
                  `${hold} sessions: ${Object.entries(value.weights)
                    .map(
                      ([model, weight]) => `${readable(model)} ${rate(weight)}`,
                    )
                    .join(
                      ", ",
                    )}${value.equal_weight_fallback ? " (equal-weight fallback)" : ""}`,
              )
              .join("; ") || "Unavailable",
          baseline: [1, 3, 5]
            .map(
              (hold, index) =>
                `${hold} sessions: ${amount(row.calibration?.baseline_mse?.[index], 8)} / ${amount(row.calibration?.baseline_mse?.[index + 3], 8)}`,
            )
            .join("; "),
          model_error:
            Object.entries(row.calibration?.model_mse ?? {})
              .map(
                ([model, values]) =>
                  `${readable(model)}: ${[1, 3, 5].map((hold, index) => `${hold}s ${amount(values[index], 8)} / ${amount(values[index + 3], 8)}`).join(", ")}`,
              )
              .join("; ") || "Unavailable",
          warnings: row.warnings?.join("; ") || "None reported",
        }))}
      />
    </details>
  );
}

function TradingMetrics({ row }: { row: Portfolio }) {
  const metrics = row.trade_metrics;
  if (!metrics) return null;
  if (row.status !== "complete")
    return (
      <p>
        {number(metrics.completed_trades, 0)} completed round trips before this
        test stopped. Trade profitability and period statistics are unavailable
        for the incomplete account.
      </p>
    );
  return (
    <section aria-label="Short-hold trading statistics">
      <h4>Actual trading activity</h4>
      <dl className="historical-trade-metrics">
        <div>
          <dt>Completed round trips</dt>
          <dd>{number(metrics.completed_trades, 0)}</dd>
          <small>{amount(metrics.trades_per_week)} per 5 sessions</small>
        </div>
        <div>
          <dt>Average holding time</dt>
          <dd>{amount(metrics.mean_holding_sessions)} sessions</dd>
          <small>
            {amount(metrics.mean_holding_calendar_days)} calendar days
          </small>
        </div>
        <div>
          <dt>Net expectancy per trade</dt>
          <dd>
            {row.currency} {amount(metrics.net_expectancy_native)}
          </dd>
          <small>
            {rate(metrics.net_expectancy_return)} average net trade return
          </small>
        </div>
        <div>
          <dt>Winning trades</dt>
          <dd>{rate(metrics.win_rate)}</dd>
          <small>After modeled trading costs</small>
        </div>
        <div>
          <dt>Annualized turnover</dt>
          <dd>{amount(metrics.annualized_turnover)}×</dd>
          <small>Entry + exit notional / mean equity</small>
        </div>
        <div>
          <dt>Average invested fraction</dt>
          <dd>{rate(metrics.mean_exposure_fraction)}</dd>
          <small>Remaining equity is cash</small>
        </div>
      </dl>
      {row.period_metrics && (
        <>
          <h4>Account results by calendar period</h4>
          <Table
            columns={[
              ["period", "Period"],
              ["count", "Periods observed"],
              ["profitable", "Profitable periods"],
              ["average", "Average return"],
              ["median", "Median return"],
              ["worst", "Worst return"],
            ]}
            rows={(["weekly", "monthly"] as const).flatMap((period) => {
              const values = row.period_metrics?.[period];
              return values
                ? [
                    {
                      period: readable(period),
                      count: number(values.count, 0),
                      profitable: rate(values.profitable_fraction),
                      average: rate(values.mean_return),
                      median: rate(values.median_return),
                      worst: rate(values.worst_return),
                    },
                  ]
                : [];
            })}
          />
          <p>
            These are whole-account returns, including time spent in cash and
            the first and last partial calendar periods.
          </p>
        </>
      )}
    </section>
  );
}

export default function HistoricalResearchPanel({ request, error }: Props) {
  const [state, setState] = useState<Status>({ status: "loading" });
  const [result, setResult] = useState<Result | null>(null);
  const [currency, setCurrency] = useState("USD");
  const [budget, setBudget] = useState(500);
  const [cost, setCost] = useState(40);
  const [busy, setBusy] = useState(false);
  const [studyMode, setStudyMode] = useState("multi_model");
  const [modelPortfolio, setModelPortfolio] = useState("");
  const [reuseCapture, setReuseCapture] = useState(true);
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
      setState(
        await request("/historical-lab/start", {
          study_mode: studyMode,
          ...(reuseCapture && result ? { source_run_id: result.run_id } : {}),
        }),
      );
    } catch (failure) {
      error((failure as Error).message);
    } finally {
      setBusy(false);
    }
  }
  const multiModel = result?.study_mode === "multi_model";
  const shortHold =
    multiModel ||
    result?.study_mode === "short_horizon" ||
    result?.methodology.version === "daily-short-hold-v1";
  const budgets = result?.methodology.budgets ?? [500, 2000, 10000, 100000];
  const costs = result?.methodology.cost_bps ?? [20, 40, 100];
  const selectedBudget = budgets.includes(budget) ? budget : budgets[0];
  const selectedCost = costs.includes(cost) ? cost : costs[0];
  const matches = (row: Portfolio) =>
    row.currency === currency &&
    row.budget === selectedBudget &&
    row.cost_bps === selectedCost;
  const portfolios = result?.portfolios.filter(matches) ?? [];
  const rows = [
    ...portfolios,
    ...(result?.benchmarks
      .filter(matches)
      .map((r) => ({ ...r, strategy: `${r.symbol} buy and hold` })) ?? []),
  ];
  const walk = multiModel
    ? (portfolios.find((row) => portfolioKey(row) === modelPortfolio) ??
      portfolios[0])
    : result?.walk_forward.find(matches);
  const benchmark =
    walk?.benchmark ??
    (multiModel
      ? result?.benchmarks.find(
          (row) =>
            matches(row) &&
            row.symbol !== "CASH" &&
            row.first_session === walk?.first_session &&
            row.last_session === walk?.last_session,
        )
      : undefined);
  const compareBenchmark =
    walk?.status === "complete" &&
    benchmark?.status === "complete" &&
    walk.first_session === benchmark.first_session &&
    walk.last_session === benchmark.last_session;
  const chartSeries = walk
    ? [
        {
          name: `${multiModel ? readable(walk.strategy) : "Rolling selection"}${walk.status === "complete" ? "" : " (partial history)"}`,
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
                points: (benchmark?.monthly_equity_curve ?? [])
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
            Daily market history from 2000 where available · cash accounts ·
            costs and settlement modeled
          </p>
        </div>
        <div className="lab-actions historical-run-actions">
          <label>
            Study to run
            <select
              value={studyMode}
              disabled={active || busy}
              onChange={(event) => setStudyMode(event.target.value)}
            >
              <option value="multi_model">
                Rolling models · 1 / 3 / 5 sessions
              </option>
              <option value="short_horizon">
                Daily screening · 1 / 3 / 5 sessions
              </option>
              <option value="legacy">Baseline · 5 / 10 / 20 sessions</option>
            </select>
          </label>
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
              : studyMode === "multi_model"
                ? "Run model study"
                : studyMode === "short_horizon"
                  ? "Run short-hold study"
                  : "Run baseline study"}
          </button>
        </div>
      </div>
      {result && (
        <label className="historical-reuse-capture">
          <input
            type="checkbox"
            checked={reuseCapture}
            disabled={active || busy}
            onChange={(event) => setReuseCapture(event.target.checked)}
          />
          Reuse the saved histories from the result below
        </label>
      )}
      <p>
        The model study compares rolling forecasts with daily trading rules,
        using 1, 3, or 5-session positions. All current modes use daily bars;
        they do not simulate intraday or hourly execution.
      </p>
      <div role="status" aria-live="polite" className="operator-state">
        <span className="badge synthetic">Historical research</span>
        <h3>
          {readable(state.status)}
          {state.phase
            ? ` · ${readable(state.phase === "evaluation" ? (state.stage ?? state.phase) : state.phase)}`
            : ""}
        </h3>
        {active && state.study_mode && (
          <p>
            {state.study_mode === "multi_model"
              ? "Running rolling model forecasts with separate fitting, calibration and test windows."
              : state.study_mode === "short_horizon"
                ? "Running daily screening with 1 / 3 / 5-session holds."
                : "Running the 5 / 10 / 20-session baseline."}
          </p>
        )}
        {active && state.run_id && (
          <p className="lab-timestamp">Active run {state.run_id}</p>
        )}
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
        {active && state.phase === "evaluation" && (
          <p>
            {state.currency}
            {(state.stage === "historical_features" ||
              state.stage === "ensemble_features") &&
            state.symbols != null
              ? ` · ${number(state.symbols, 0)} instrument features prepared`
              : (state.stage?.endsWith("portfolios") ||
                    state.stage?.endsWith("walk_forward")) &&
                  state.budget != null
                ? ` · ${number(state.budget, 0)} starting cash`
                : ""}
            {(state.stage?.endsWith("walk_forward") ||
              state.stage === "ensemble_fit") &&
            state.test_start
              ? ` · test window starting ${state.test_start}`
              : ""}
            {state.stage === "ensemble_fit" && state.fold != null
              ? ` · fold ${state.fold}${state.total_folds != null ? ` / ${state.total_folds}` : ""}`
              : ""}
            {state.stage === "ensemble_portfolios" && state.model
              ? ` · ${readable(state.model)}`
              : ""}
          </p>
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
          <h3>
            {multiModel
              ? "Rolling model study results"
              : shortHold
                ? "Daily short-hold results"
                : "Baseline historical results"}
          </h3>
          {active && (
            <p className="historical-retained-result">
              A new study is running. The previously published results remain
              below until the new study finishes.
            </p>
          )}
          <p className="lab-timestamp">
            Published {result.created_at} · Run {result.run_id}
          </p>
          <p>
            {number(result.capture.usable, 0)} histories ·{" "}
            {number(result.capture.rows, 0)} daily observations ·{" "}
            {number(result.methodology.attempts.length, 0)} declared{" "}
            {multiModel ? "model and rule comparisons" : "strategy variants"}.
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
                value={selectedBudget}
                onChange={(e) => setBudget(Number(e.target.value))}
              >
                {budgets.map((v) => (
                  <option key={v} value={v}>
                    {number(v, 0)}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Historical round-trip cost{" "}
              <select
                value={selectedCost}
                onChange={(e) => setCost(Number(e.target.value))}
              >
                {costs.map((v) => (
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
          {shortHold && (
            <p>
              Daily screening · next-session close execution · target holds of{" "}
              {(result.methodology.horizons ?? [1, 3, 5]).join(", ")} sessions.
              Positions enter and exit independently as settled cash permits.
            </p>
          )}
          {multiModel ? (
            <>
              <h3>Continuous portfolios from rolling forecasts</h3>
              <p>
                Each model is fitted and calibrated using prior outcomes, then
                evaluated on the following test window. These accounts continue
                across successive windows with daily decisions and short holds.
                The comparison rules remain visible alongside learned models.
                This is retrospective research on previously examined data.
              </p>
              <label>
                Model or comparison portfolio
                <select
                  value={walk ? portfolioKey(walk) : ""}
                  onChange={(event) => setModelPortfolio(event.target.value)}
                >
                  {portfolios.map((row) => (
                    <option key={portfolioKey(row)} value={portfolioKey(row)}>
                      {readable(row.strategy)} · {row.horizon} sessions
                    </option>
                  ))}
                </select>
              </label>
              <ModelDiagnostics
                rows={(result.model_diagnostics ?? []).filter(
                  (row) => row.currency === currency,
                )}
              />
            </>
          ) : (
            <>
              <h3>Training-only selection, tested on the following year</h3>
              <p>
                Each selection uses the previous three years. Test periods keep
                their selected rule; cash remains an eligible choice. These are
                retrospective tests designed today, with current listing and
                data limitations.
                {shortHold &&
                  " The rule is selected annually; trading decisions are made daily within each test year."}
              </p>
            </>
          )}
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
                {rate(completedValue(walk, walk.total_return))} · maximum
                drawdown {rate(completedValue(walk, walk.max_drawdown))} ·
                annualized return {rate(completedValue(walk, walk.cagr))} ·{" "}
                {number(walk.trade_metrics?.completed_trades ?? walk.trades, 0)}{" "}
                {walk.trade_metrics ? "completed round trips" : "trades"}
              </p>
              {compareBenchmark && (
                <p>
                  Same-period benchmark return: {rate(benchmark?.total_return)}{" "}
                  · drawdown: {rate(benchmark?.max_drawdown)}.
                </p>
              )}
              {walk.status === "complete" && (walk.max_drawdown ?? 0) > 0.3 && (
                <p>This test exceeds your 30% maximum loss tolerance.</p>
              )}
              <TradingMetrics row={walk} />
              {!multiModel && (
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
              )}
            </>
          ) : (
            <p>
              {multiModel
                ? "No model portfolio is available for this selection."
                : "No rolling test is available for this selection."}
            </p>
          )}
          {multiModel && (
            <details>
              <summary>
                Latest research forecasts for this model and hold
              </summary>
              <p>
                Saved forecasts from the study cutoff, not current quotes or
                qualified buy recommendations. The score uses the declared
                40-bps scenario regardless of the cost filter above.
              </p>
              <Table
                columns={[
                  ["rank", "Rank"],
                  ["symbol", "Symbol"],
                  ["session", "As of session"],
                  ["price", `Price (${currency})`],
                  ["return", "Predicted return"],
                  ["downside", "Predicted downside"],
                  ["score", "Score at 40 bps"],
                ]}
                rows={(result.latest_candidates ?? [])
                  .filter(
                    (row) =>
                      row.currency === currency &&
                      row.strategy === walk?.strategy &&
                      row.horizon === walk?.horizon,
                  )
                  .map((row) => ({
                    rank: number(row.rank, 0),
                    symbol: row.symbol,
                    session: row.session,
                    price: amount(row.price),
                    return: rate(row.predicted_return),
                    downside: rate(row.predicted_downside),
                    score: rate(row.score_40bps),
                  }))}
              />
            </details>
          )}
          <h3>
            {multiModel
              ? "All rolling model portfolios, rules and benchmarks"
              : "All fixed strategies and benchmarks"}
          </h3>
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
              ["trades", shortHold ? "Completed round trips" : "Trades"],
              ["fees", `Fees (${currency})`],
              ...(shortHold
                ? ([
                    ["average_hold", "Average hold (sessions)"],
                    ["expectancy", `Net expectancy (${currency}/trade)`],
                    ["win_rate", "Winning trades"],
                    ["turnover", "Annualized turnover"],
                  ] as [string, string][])
                : []),
            ]}
            rows={rows.map((r) => ({
              rule: readable(r.strategy),
              hold: r.horizon ? `${r.horizon} sessions` : "—",
              status: readable(r.status),
              total: rate(completedValue(r, r.total_return)),
              drawdown: rate(completedValue(r, r.max_drawdown)),
              annual: rate(completedValue(r, r.cagr)),
              trades: number(r.trade_metrics?.completed_trades ?? r.trades, 0),
              fees: number(r.fees, 2),
              average_hold: amount(
                completedValue(r, r.trade_metrics?.mean_holding_sessions),
              ),
              expectancy: amount(
                completedValue(r, r.trade_metrics?.net_expectancy_native),
              ),
              win_rate: rate(completedValue(r, r.trade_metrics?.win_rate)),
              turnover:
                r.status === "complete" &&
                r.trade_metrics?.annualized_turnover != null
                  ? `${amount(r.trade_metrics.annualized_turnover)}×`
                  : "Unavailable",
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
