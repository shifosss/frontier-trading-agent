import { useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import "./style.css";
import ResearchPanel from "./ResearchPanel";
import ScannerPanel from "./ScannerPanel";
import { Download, EquityChart, Table } from "./StudyDisplay";
import { day, number, percent } from "./format";
import type { Dataset } from "./types";
type Obj = Record<string, any>;
const label = (s: string) =>
  s === "synthetic_fixture" ? "Synthetic fixture" : "Historical snapshot";
const evidence = (s: string) =>
  ({
    exploratory_raw_price: "Exploratory raw-price study",
    exploratory_incomplete_actions:
      "Exploratory study · incomplete action coverage",
    synthetic_engineering: "Synthetic engineering fixture",
    limited_raw_price_replay: "Limited raw-price replay",
  })[s] ?? s;
async function api(path: string, body?: unknown) {
  const r = await fetch(
    `/api${path}`,
    body === undefined
      ? undefined
      : {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body),
        },
  );
  const j = await r.json();
  if (!r.ok)
    throw Error(
      typeof j.detail === "string" ? j.detail : JSON.stringify(j.detail ?? j),
    );
  return j;
}
const pages = [
  {
    id: "Scanner",
    icon: "⌕",
    title: "Market scanner",
    description:
      "Find candidates, size a simulated basket, and examine the evidence.",
  },
  {
    id: "Study",
    icon: "◷",
    title: "Research study",
    description: "From an explicit hypothesis to an inspectable result.",
  },
  {
    id: "Data",
    icon: "▤",
    title: "Data",
    description: "Know the source, timing and limits of every observation.",
  },
  {
    id: "Experiments",
    icon: "⤨",
    title: "Experiments",
    description: "Inspect every attempt and compare like-for-like inputs.",
  },
  {
    id: "Research",
    icon: "◇",
    title: "Research",
    description: "Bounded proposals, replay feedback and frozen observations.",
  },
  {
    id: "Operations",
    icon: "⚙",
    title: "Operations",
    description: "Runtime evidence and the limits of this workstation.",
  },
] as const;
type Page = (typeof pages)[number]["id"];

function App() {
  const [page, setPage] = useState<Page>("Scanner"),
    [datasets, setDatasets] = useState<Dataset[]>([]),
    [runs, setRuns] = useState<Obj[]>([]),
    [status, setStatus] = useState<Obj | null>(null),
    [datasetId, setDatasetId] = useState(""),
    [family, setFamily] = useState("passive"),
    [lookback, setLookback] = useState(20),
    [cashUSD, setCashUSD] = useState(10000),
    [cashCAD, setCashCAD] = useState(10000),
    [base, setBase] = useState("CAD"),
    [fee, setFee] = useState(1),
    [slippage, setSlippage] = useState(5),
    [optIn, setOptIn] = useState(false),
    [busy, setBusy] = useState(""),
    [error, setError] = useState(""),
    [notice, setNotice] = useState(""),
    [active, setActive] = useState<Obj | null>(null),
    [detailTab, setDetailTab] = useState("Decisions"),
    [instrument, setInstrument] = useState(""),
    [decision, setDecision] = useState(0),
    [source, setSource] = useState("data/imports/"),
    [preview, setPreview] = useState<Obj | null>(null),
    [selected, setSelected] = useState<string[]>([]),
    [compared, setCompared] = useState<Obj[]>([]),
    [campaign, setCampaign] = useState<Obj | null>(null),
    [baselineCampaigns, setBaselineCampaigns] = useState<Obj[]>([]),
    [sort, setSort] = useState("created_at");
  const currentPage = pages.find((item) => item.id === page)!;
  const dataset = datasets.find((d) => d.dataset_id === datasetId),
    result = active?.result,
    summary = result?.summary;
  const isEarlierVersion = (record: Obj | undefined) =>
    record?.status === "COMPLETED" &&
    typeof status?.current_code_identity === "string" &&
    record.code_identity !== status.current_code_identity;
  async function refresh() {
    const [s, d, r, c] = await Promise.all([
      api("/status"),
      api("/datasets"),
      api("/runs"),
      api("/campaigns"),
    ]);
    setStatus(s);
    setDatasets(d);
    setRuns(r);
    setBaselineCampaigns(c);
    setCampaign((old) => old ?? c[0] ?? null);
    setDatasetId(
      (old) =>
        old ||
        d.find((item: Dataset) => item.mode === "synthetic_fixture")
          ?.dataset_id ||
        d[0]?.dataset_id ||
        "",
    );
  }
  useEffect(() => {
    refresh().catch((e) => setError(e.message));
    const studyId = new URLSearchParams(window.location.search).get("study");
    if (studyId) openStudy(studyId).catch((e) => setError(e.message));
  }, []);
  useEffect(() => {
    setOptIn(localStorage.getItem(`frontier-actions-${datasetId}`) === "yes");
    setPreview(null);
    setInstrument("");
    setDecision(0);
  }, [datasetId]);
  async function work(name: string, fn: () => Promise<void>) {
    setBusy(name);
    setError("");
    setNotice("");
    try {
      await fn();
      await refresh();
    } catch (e) {
      setError((e as Error).message);
      await refresh().catch(() => {});
    } finally {
      setBusy("");
    }
  }
  function updateOptIn(value: boolean) {
    setOptIn(value);
    localStorage.setItem(`frontier-actions-${datasetId}`, value ? "yes" : "no");
  }
  async function openStudy(id: string) {
    setActive(await api(`/runs/${encodeURIComponent(id)}`));
    setCompared([]);
    setPage("Study");
  }
  function importDemo(message: string) {
    return work("Importing demo", async () => {
      await api("/demo", {});
      setNotice(message);
    });
  }
  function config() {
    return {
      dataset_id: datasetId,
      strategy: {
        family,
        name: family,
        lookback,
        rebalance_every: 5,
        max_weight: 0.2,
        long_only: true,
        whole_shares: true,
        currency_funding: "separate",
      },
      initial_cash_usd: cashUSD,
      initial_cash_cad: cashCAD,
      base_currency: base,
      commission_per_order: fee,
      slippage_bps: slippage,
      seed: 1729,
      allow_incomplete_actions: optIn,
    };
  }
  function run() {
    if (!datasetId || busy) return;
    work("Running study", async () => {
      const r = await api("/runs", config());
      setActive(r);
      setCompared([]);
      setNotice("Study completed. The result and report are saved locally.");
    });
  }
  useEffect(() => {
    const key = (e: KeyboardEvent) => {
      if (e.ctrlKey && e.key === "Enter" && page === "Study") {
        e.preventDefault();
        run();
      }
    };
    window.addEventListener("keydown", key);
    return () => window.removeEventListener("keydown", key);
  });
  const filtered = (result?.decisions ?? []).filter(
      (d: Obj) => !instrument || d.instrument_id === instrument,
    ),
    chosen = filtered[decision];
  const comparisonNormalized =
    compared.length > 0 &&
    new Set(
      compared.map(
        (r) =>
          `${r.result.summary.initial_nav}/${r.result.summary.base_currency}`,
      ),
    ).size > 1;
  const series = compared.length
    ? compared.map((r, i) => ({
        name: `${r.record.config.strategy.name} / ${r.record.id.slice(0, 6)}`,
        points: r.result.equity_curve.map((p: Obj) => ({
          ...p,
          nav: comparisonNormalized
            ? (p.nav / r.result.summary.initial_nav) * 100
            : p.nav,
        })),
        color: ["#245BD3", "#167D8D", "#9A5A12", "#8457B4"][i % 4],
      }))
    : result
      ? [
          {
            name: result.config.strategy.name,
            points: result.equity_curve,
            color: "#245BD3",
          },
        ]
      : [];
  const setup = (
    <aside className="setup">
      <div className="section-heading">
        <h2>Study setup</h2>
        <span className="quiet">
          {dataset?.interval === "1h" ? "Hourly bars" : "Daily bars"}
        </span>
      </div>
      <label>
        Dataset
        <select
          value={datasetId}
          onChange={(e) => setDatasetId(e.target.value)}
        >
          {!datasets.length && <option>No dataset imported</option>}
          {datasets.map((d) => (
            <option key={d.dataset_id} value={d.dataset_id}>
              {d.name}
            </option>
          ))}
        </select>
      </label>
      {dataset && (
        <div className="dataset-note">
          <span
            className={`badge ${dataset.mode === "synthetic_fixture" ? "synthetic" : ""}`}
          >
            {label(dataset.mode)}
          </span>
          <p>
            {Array.from(
              new Set(
                dataset.instruments.map(
                  (i) =>
                    `${i.venue === "XTSE" ? "Canada" : "United States"} / ${i.currency}`,
                ),
              ),
            ).join(" + ")}
            <br />
            {day(dataset.start)} to {day(dataset.end)}
            <br />
            {dataset.row_count.toLocaleString()} bars ·{" "}
            {dataset.instruments.length} instruments
          </p>
        </div>
      )}
      <label>
        Strategy
        <select value={family} onChange={(e) => setFamily(e.target.value)}>
          <option value="passive">Passive allocation</option>
          <option value="cash">Cash only</option>
          <option value="trend">Trend following</option>
          <option value="reversion">Mean reversion</option>
        </select>
      </label>
      {["trend", "reversion"].includes(family) && (
        <label>
          Lookback ({dataset?.interval === "1h" ? "bars" : "sessions"})
          <input
            type="number"
            min="2"
            value={lookback}
            onChange={(e) => setLookback(+e.target.value)}
          />
        </label>
      )}
      <div className="field-pair">
        <label>
          Starting USD
          <input
            type="number"
            min="0"
            value={cashUSD}
            onChange={(e) => setCashUSD(+e.target.value)}
          />
        </label>
        <label>
          Starting CAD
          <input
            type="number"
            min="0"
            value={cashCAD}
            onChange={(e) => setCashCAD(+e.target.value)}
          />
        </label>
      </div>
      <div className="cost-strip">
        <strong>Execution costs</strong>
        <span>{number(fee)} native currency / order</span>
        <span>{number(slippage, 1)} bps slippage</span>
      </div>
      <details>
        <summary>Advanced settings</summary>
        <label>
          Reporting currency
          <select value={base} onChange={(e) => setBase(e.target.value)}>
            <option>CAD</option>
            <option>USD</option>
          </select>
        </label>
        <label>
          Commission per order
          <input
            type="number"
            min="0"
            step="0.1"
            value={fee}
            onChange={(e) => setFee(+e.target.value)}
          />
        </label>
        <label>
          Slippage (basis points)
          <input
            type="number"
            min="0"
            step="0.1"
            value={slippage}
            onChange={(e) => setSlippage(+e.target.value)}
          />
        </label>
      </details>
      {dataset?.corporate_actions_status === "unknown" && (
        <label className="check warning">
          <input
            type="checkbox"
            checked={optIn}
            onChange={(e) => updateOptIn(e.target.checked)}
          />
          <span>
            Allow exploratory raw-price study. Distributions may be omitted;
            this is not total return.
          </span>
        </label>
      )}
      <button
        className="primary run-button"
        disabled={!!busy || !datasetId}
        onClick={run}
      >
        {busy === "Running study" ? "Running study…" : "Run study"}
        <span>Ctrl + Enter</span>
      </button>
      <button
        className="secondary"
        disabled={!!busy || !datasetId}
        onClick={() =>
          work("Comparing baselines", async () => {
            const c = await api("/campaigns", {
              dataset_id: datasetId,
              allow_incomplete_actions: optIn,
            });
            setCampaign(c);
            setPage("Experiments");
            setNotice(
              `${c.trial_count} declared trials completed. This tournament is exploratory.`,
            );
          })
        }
      >
        Compare baselines
      </button>
      <p className="fine">
        Baseline comparison runs 11 declared trials: cash, passive,
        trend/reversion at 10/20/40 sessions, plus 3 cost-stress trials. USD
        10,000 + CAD 10,000 each; fee 1 / order and 5 bps, doubled for stress
        trials. Long only. Whole shares. At most 20% per exposure group at
        sizing. Separate USD/CAD funding. Signals execute at the next eligible
        opening.
      </p>
    </aside>
  );
  return (
    <div className="app">
      <aside className="rail">
        <a className="brand" href="#" onClick={(e) => e.preventDefault()}>
          <span className="brand-mark">F</span>
          <span>
            Frontier<small>Research</small>
          </span>
        </a>
        <nav aria-label="Main navigation">
          {pages.map((item) => (
            <button
              key={item.id}
              className={page === item.id ? "active" : ""}
              onClick={() => setPage(item.id)}
            >
              <span className="nav-icon" aria-hidden="true">
                {item.icon}
              </span>
              {item.id}
            </button>
          ))}
        </nav>
        <div className="rail-foot">
          <span className="status-dot" />
          Local workspace
          <small>
            Research only
            <br />
            No broker connection
          </small>
        </div>
      </aside>
      <main>
        <header>
          <div>
            <h1>{currentPage.title}</h1>
            <p>{currentPage.description}</p>
          </div>
          <div className="service">
            <span className="status-dot" />
            {status ? "Local service ready" : "Connecting"}
            <small>Nautilus {status?.engine?.version ?? "—"}</small>
          </div>
        </header>
        {error && (
          <div className="feedback error" role="alert">
            <strong>Unable to complete request</strong>
            <p>{error}</p>
            <span>
              {error.toLowerCase().includes("split") ||
              error.toLowerCase().includes("dividend")
                ? "This study cannot account for the reported corporate action with its current inputs. Inspect the dataset's action details in Data; changing strategy parameters will not repair the missing accounting."
                : "The request was not completed. Inspect the reported detail before retrying; saved study attempts remain available in Experiments or Research."}
            </span>
            <button aria-label="Dismiss error" onClick={() => setError("")}>
              ×
            </button>
          </div>
        )}
        {notice && (
          <div className="feedback success" role="status">
            {notice}
            <button aria-label="Dismiss message" onClick={() => setNotice("")}>
              ×
            </button>
          </div>
        )}
        {busy && (
          <div className="working" role="status">
            {busy}…{" "}
            {busy === "Scanning US and Canadian markets"
              ? "Retrieving completed sessions and testing historical selections. This may take a minute."
              : busy === "Exploring with Codex"
                ? "The bounded request may take several minutes. Completed attempts are saved."
                : [
                      "Running study",
                      "Rerunning saved settings",
                      "Comparing baselines",
                    ].includes(busy)
                  ? "Actual replay is in progress."
                  : "Waiting for the requested operation to complete."}
          </div>
        )}
        {page === "Scanner" && (
          <ScannerPanel
            busy={busy}
            request={api}
            work={work}
            notice={setNotice}
            error={setError}
          />
        )}
        {page === "Study" && (
          <div className="study-layout">
            <div className="study-results">
              {isEarlierVersion(active?.record) && (
                <p className="version-notice" role="status">
                  Saved with an earlier research version. Rerun saved settings
                  to use the current version.
                </p>
              )}
              <section className="chart-sheet">
                <div className="section-heading">
                  <div>
                    <h2>Portfolio equity</h2>
                    <p>
                      {comparisonNormalized
                        ? "Normalized starting NAV = 100"
                        : `Net asset value${summary ? ` / ${summary.base_currency}` : ""}`}
                    </p>
                  </div>
                  {summary && (
                    <span className="badge synthetic">
                      {summary.evidence_label
                        ? evidence(summary.evidence_label)
                        : label(summary.mode)}
                    </span>
                  )}
                </div>
                <EquityChart
                  series={series}
                  currency={
                    comparisonNormalized
                      ? "index (initial NAV = 100)"
                      : (summary?.base_currency ?? base)
                  }
                />
                <div className="metric-strip">
                  {[
                    [
                      summary?.total_return == null &&
                      summary?.raw_price_return != null
                        ? summary.return_basis ===
                          "raw_price_plus_gross_cash_dividends"
                          ? "Exploratory return"
                          : "Simulated raw-price return"
                        : "Net return",
                      summary
                        ? percent(
                            summary.total_return ?? summary.raw_price_return,
                          )
                        : "—",
                    ],
                    [
                      "Max drawdown",
                      summary ? percent(summary.max_drawdown) : "—",
                    ],
                    ["Fills", summary ? number(summary.trade_count, 0) : "—"],
                    [
                      "Final NAV",
                      summary
                        ? `${number(summary.final_nav)} ${summary.base_currency}`
                        : "—",
                    ],
                  ].map(([l, v]) => (
                    <div key={l}>
                      <span>{l}</span>
                      <strong>{v}</strong>
                    </div>
                  ))}
                </div>
              </section>
              {result ? (
                <>
                  <div className="result-toolbar">
                    <span>
                      Saved study{" "}
                      <strong>{active!.record.id.slice(0, 8)}</strong> ·{" "}
                      {result.dataset.name}
                    </span>
                    <div>
                      <a
                        href={`/api/runs/${active!.record.id}/report`}
                        target="_blank"
                        rel="noreferrer"
                      >
                        Open report
                      </a>
                      <button
                        className="text-button"
                        disabled={!!busy}
                        onClick={() =>
                          work("Rerunning saved settings", async () => {
                            const rerun = await api(
                              "/runs",
                              active!.record.config,
                            );
                            setActive(rerun);
                            setCompared([]);
                            setInstrument("");
                            setDecision(0);
                            setNotice(
                              "New study completed using the saved settings and current engine code. Its configuration can now be frozen for observation.",
                            );
                          })
                        }
                      >
                        Rerun saved settings
                      </button>
                      <button
                        className="text-button"
                        disabled={!!busy}
                        onClick={() =>
                          work("Freezing configuration", async () => {
                            await api("/frozen", { run_id: active!.record.id });
                            setNotice(
                              "Configuration frozen for observation. Open Research to inspect it or record an observation.",
                            );
                          })
                        }
                      >
                        Freeze for observation
                      </button>
                      <Download
                        value={result.config}
                        name="frontier-config.json"
                      >
                        Config
                      </Download>
                      <Download value={result} name="frontier-result.json">
                        Result
                      </Download>
                    </div>
                  </div>
                  <section className="detail-sheet">
                    <div className="tabs" role="tablist">
                      {["Decisions", "Fills", "Holdings", "Assumptions"].map(
                        (t) => (
                          <button
                            role="tab"
                            aria-selected={detailTab === t}
                            className={detailTab === t ? "active" : ""}
                            key={t}
                            onClick={() => setDetailTab(t)}
                          >
                            {t}
                          </button>
                        ),
                      )}
                    </div>
                    {detailTab === "Decisions" && (
                      <>
                        <div className="decision-controls">
                          <label>
                            Instrument
                            <select
                              value={instrument}
                              onChange={(e) => {
                                setInstrument(e.target.value);
                                setDecision(0);
                              }}
                            >
                              <option value="">All instruments</option>
                              {result.dataset.instruments.map((i: Obj) => (
                                <option key={i.id}>{i.id}</option>
                              ))}
                            </select>
                          </label>
                          <label>
                            Decision time
                            <select
                              value={decision}
                              onChange={(e) => setDecision(+e.target.value)}
                            >
                              {filtered.map((d: Obj, i: number) => (
                                <option value={i} key={i}>
                                  {d.decision_time} / {d.instrument_id}
                                </option>
                              ))}
                            </select>
                          </label>
                        </div>
                        {chosen ? (
                          <div className="decision-inspect">
                            <div>
                              <span>Permitted input</span>
                              <strong>
                                {chosen.input_event_time ??
                                  "No observed history"}
                              </strong>
                              <small>
                                Available {chosen.available_at ?? "—"}
                              </small>
                            </div>
                            <div>
                              <span>Signal / target</span>
                              <strong>
                                {String(chosen.signal)} /{" "}
                                {percent(chosen.target_weight)}
                              </strong>
                              <small>{chosen.reason}</small>
                            </div>
                            <div>
                              <span>Next execution</span>
                              <strong>
                                {chosen.execution_time ??
                                  "Unfilled at sample end"}
                              </strong>
                              <small>{chosen.instrument_id}</small>
                            </div>
                          </div>
                        ) : (
                          <p className="empty-small">
                            No decisions were emitted.
                          </p>
                        )}
                        {chosen && (
                          <Table
                            rows={result.fills.filter(
                              (f: Obj) =>
                                f.instrument_id === chosen.instrument_id &&
                                f.decision_time === chosen.decision_time,
                            )}
                            columns={[
                              ["timestamp", "Actual fill time"],
                              ["side", "Side"],
                              ["quantity", "Shares"],
                              ["price", "Price"],
                              ["commission", "Fee"],
                              ["currency", "Currency"],
                            ]}
                          />
                        )}
                      </>
                    )}
                    {detailTab === "Fills" && (
                      <>
                        <p className="table-intro">
                          Actual engine fills. Price and fee use each
                          instrument’s native currency.
                        </p>
                        <Table
                          rows={result.fills}
                          columns={[
                            ["timestamp", "Timestamp (UTC)"],
                            ["instrument_id", "Instrument"],
                            ["side", "Side"],
                            ["quantity", "Shares"],
                            ["price", "Price"],
                            ["commission", "Fee"],
                            ["currency", "Currency"],
                          ]}
                        />
                      </>
                    )}
                    {detailTab === "Holdings" && (
                      <>
                        <div className="balance-line">
                          Cash: {number(result.balances.USD)} USD /{" "}
                          {number(result.balances.CAD)} CAD
                        </div>
                        <Table
                          rows={result.positions}
                          columns={[
                            ["instrument_id", "Instrument"],
                            ["quantity", "Shares"],
                            ["average_basis", "Average basis"],
                            ["mark", "Last mark"],
                            ["currency", "Currency"],
                          ]}
                        />
                      </>
                    )}
                    {detailTab === "Assumptions" && (
                      <div className="assumptions">
                        <p>
                          Fees: {number(summary.fees.USD)} USD /{" "}
                          {number(summary.fees.CAD)} CAD. Average exposure{" "}
                          {percent(summary.average_exposure)}. Sharpe{" "}
                          {number(summary.sharpe)}.
                        </p>
                        {summary.dividend_income && (
                          <p>
                            Gross dividends earned:{" "}
                            {number(summary.dividend_income.USD)} USD /{" "}
                            {number(summary.dividend_income.CAD)} CAD.
                            {summary.dividend_receivables && (
                              <>
                                {" "}
                                Unpaid at study end:{" "}
                                {number(summary.dividend_receivables.USD)} USD /{" "}
                                {number(summary.dividend_receivables.CAD)} CAD.
                              </>
                            )}
                          </p>
                        )}
                        <ul>
                          {summary.limitations.map((l: string) => (
                            <li key={l}>{l}</li>
                          ))}
                        </ul>
                        <p>Engine identity</p>
                        <pre>
                          {JSON.stringify(result.engine_identity, null, 2)}
                        </pre>
                      </div>
                    )}
                  </section>
                </>
              ) : (
                <div className="empty-guidance">
                  <strong>A result you can retrace</strong>
                  <p>
                    Every study saves the exact dataset, settings, signals,
                    native-currency fills and an offline report.
                  </p>
                  {!datasets.length && (
                    <button
                      className="secondary"
                      disabled={!!busy}
                      onClick={() =>
                        importDemo(
                          "Synthetic engineering fixture imported. It does not represent market performance.",
                        )
                      }
                    >
                      Import engineering demo
                    </button>
                  )}
                </div>
              )}
            </div>
            {setup}
          </div>
        )}
        {page === "Data" && (
          <>
            <section className="wide-sheet">
              <div className="section-heading">
                <h2>Local datasets</h2>
                <button
                  className="secondary compact"
                  disabled={!!busy}
                  onClick={() =>
                    importDemo("Synthetic engineering fixture is available.")
                  }
                >
                  Import engineering demo
                </button>
              </div>
              <div className="dataset-list">
                {datasets.map((d) => (
                  <button
                    className={
                      datasetId === d.dataset_id
                        ? "dataset-row selected"
                        : "dataset-row"
                    }
                    key={d.dataset_id}
                    onClick={() => {
                      setDatasetId(d.dataset_id);
                      work("Loading dataset", async () =>
                        setPreview(await api(`/datasets/${d.dataset_id}`)),
                      );
                    }}
                  >
                    <span>
                      <strong>{d.name}</strong>
                      <small>{d.instruments.map((i) => i.id).join(", ")}</small>
                    </span>
                    <span
                      className={`badge ${d.mode === "synthetic_fixture" ? "synthetic" : ""}`}
                    >
                      {label(d.mode)}
                    </span>
                    <span>
                      {day(d.start)} — {day(d.end)}
                      <small>{d.row_count.toLocaleString()} bars</small>
                    </span>
                  </button>
                ))}
              </div>
              {dataset && (
                <div className="data-detail">
                  <h3>{dataset.name}</h3>
                  <dl>
                    <dt>Source</dt>
                    <dd>{dataset.source}</dd>
                    <dt>Last observation</dt>
                    <dd>{dataset.end}</dd>
                    <dt>Fetched</dt>
                    <dd>{dataset.retrieved_at}</dd>
                    <dt>Availability</dt>
                    <dd>{dataset.availability_basis}</dd>
                    <dt>Corporate actions</dt>
                    <dd>{dataset.corporate_actions_status}</dd>
                    <dt>Calendars / FX</dt>
                    <dd>
                      Official listing calendars. Dated USD/CAD observations,
                      available as of valuation. No automatic currency
                      conversion.
                    </dd>
                    <dt>Version</dt>
                    <dd className="digest">{dataset.dataset_id}</dd>
                  </dl>
                  <ul>
                    {dataset.limitations.map((l: string) => (
                      <li key={l}>{l}</li>
                    ))}
                  </ul>
                  {preview && (
                    <Table
                      rows={preview.preview?.bars ?? []}
                      columns={[
                        ["instrument_id", "Instrument"],
                        ["event_time", "Observation (UTC)"],
                        ["available_at", "Available (UTC)"],
                        ["close", "Close"],
                        ["volume", "Volume"],
                      ]}
                    />
                  )}
                </div>
              )}
            </section>
            <section className="wide-sheet import-sheet">
              <h2>Import a source folder</h2>
              <p>
                Place a folder inside this workspace’s <code>data/imports</code>{" "}
                or <code>data/raw</code>. Include <code>dataset.json</code> and{" "}
                <code>bars.csv</code>; provide <code>actions.csv</code> and{" "}
                <code>fx.csv</code> when available. Files are validated before
                immutable import.
              </p>
              <div className="import-controls">
                <label>
                  Source folder
                  <input
                    value={source}
                    onChange={(e) => setSource(e.target.value)}
                    placeholder="data/imports/my-dataset"
                  />
                </label>
                <button
                  className="primary"
                  disabled={!!busy}
                  onClick={() =>
                    work("Importing dataset", async () => {
                      const d = await api("/import", {
                        source_directory: source,
                      });
                      setDatasetId(d.dataset_id);
                      setNotice("Dataset validated and imported.");
                    })
                  }
                >
                  Import dataset
                </button>
              </div>
            </section>
          </>
        )}
        {page === "Experiments" && (
          <>
            <section className="wide-sheet">
              <div className="section-heading">
                <h2>
                  Study registry <span className="count">{runs.length}</span>
                </h2>
                <div className="experiment-controls">
                  <label>
                    Sort
                    <select
                      value={sort}
                      onChange={(e) => setSort(e.target.value)}
                    >
                      <option value="created_at">Newest first</option>
                      <option value="return">Replay return</option>
                      <option value="status">Status</option>
                    </select>
                  </label>
                  <button
                    className="secondary compact"
                    disabled={selected.length < 2 || !!busy}
                    onClick={() =>
                      work("Loading comparison", async () => {
                        const loaded = await Promise.all(
                          selected.map((id) => api(`/runs/${id}`)),
                        );
                        if (
                          new Set(loaded.map((r) => r.record.config.dataset_id))
                            .size > 1
                        )
                          throw Error(
                            "Choose studies from the same dataset version to compare.",
                          );
                        setCompared(loaded);
                        setActive(loaded[0]);
                        setPage("Study");
                        setNotice(
                          "Comparison loaded. Different starting NAVs or currencies are indexed to 100; original funding and costs appear below.",
                        );
                      })
                    }
                  >
                    Compare selected ({selected.length})
                  </button>
                </div>
              </div>
              {!runs.length ? (
                <p className="empty-small">
                  No studies yet. Run a study from the Study view.
                </p>
              ) : (
                <div className="table-scroll">
                  <table>
                    <thead>
                      <tr>
                        <th>Select</th>
                        <th>Study / evidence</th>
                        <th>Status</th>
                        <th>Replay return / basis</th>
                        <th>Costs / funding</th>
                        <th>Created</th>
                        <th>Inspect</th>
                      </tr>
                    </thead>
                    <tbody>
                      {[...runs]
                        .sort((a, b) =>
                          sort === "return"
                            ? (b.summary?.total_return ??
                                b.summary?.raw_price_return ??
                                -Infinity) -
                              (a.summary?.total_return ??
                                a.summary?.raw_price_return ??
                                -Infinity)
                            : sort === "status"
                              ? a.status.localeCompare(b.status)
                              : b.created_at.localeCompare(a.created_at),
                        )
                        .map((r) => (
                          <tr key={r.id}>
                            <td>
                              <input
                                aria-label={`Compare ${r.id}`}
                                type="checkbox"
                                disabled={r.status !== "COMPLETED"}
                                checked={selected.includes(r.id)}
                                onChange={(e) =>
                                  setSelected((s) =>
                                    e.target.checked
                                      ? [...s, r.id]
                                      : s.filter((id) => id !== r.id),
                                  )
                                }
                              />
                            </td>
                            <td>
                              <strong>{r.config.strategy.name}</strong>
                              {isEarlierVersion(r) && (
                                <small className="earlier-version">
                                  Earlier version
                                </small>
                              )}
                              <small>
                                {label(r.mode)} / {r.id.slice(0, 8)}
                              </small>
                            </td>
                            <td>
                              <span
                                className={`badge ${r.status === "FAILED" ? "failed" : ""}`}
                              >
                                {r.status.toLowerCase()}
                              </span>
                            </td>
                            <td>
                              {r.summary
                                ? percent(
                                    r.summary.total_return ??
                                      r.summary.raw_price_return,
                                  )
                                : "—"}
                              {r.summary && (
                                <small>
                                  {r.summary.total_return == null
                                    ? r.summary.return_basis ===
                                      "raw_price_plus_gross_cash_dividends"
                                      ? "Exploratory return"
                                      : "Simulated raw-price return"
                                    : "Replay return"}
                                </small>
                              )}
                            </td>
                            <td>
                              {r.config.commission_per_order} / order;{" "}
                              {r.config.slippage_bps} bps
                              <small>
                                {number(r.config.initial_cash_usd, 0)} USD +{" "}
                                {number(r.config.initial_cash_cad, 0)} CAD
                              </small>
                            </td>
                            <td>{day(r.created_at)}</td>
                            <td>
                              {r.status === "FAILED" ? (
                                <details>
                                  <summary>Error</summary>
                                  <p className="failure-copy">{r.error}</p>
                                </details>
                              ) : (
                                <button
                                  className="text-button"
                                  onClick={() =>
                                    work("Opening study", () => openStudy(r.id))
                                  }
                                >
                                  Open
                                </button>
                              )}
                            </td>
                          </tr>
                        ))}
                    </tbody>
                  </table>
                </div>
              )}
            </section>
            {campaign && (
              <section className="wide-sheet">
                <div className="section-heading">
                  <h2>Exploratory baseline tournament</h2>
                  <label>
                    Saved tournament
                    <select
                      value={campaign.campaign_id}
                      onChange={(e) =>
                        setCampaign(
                          baselineCampaigns.find(
                            (c) => c.campaign_id === e.target.value,
                          ) ?? campaign,
                        )
                      }
                    >
                      {baselineCampaigns.map((c) => (
                        <option key={c.campaign_id} value={c.campaign_id}>
                          {c.created_at.slice(0, 16).replace("T", " ")} /{" "}
                          {c.trial_count} trials
                        </option>
                      ))}
                    </select>
                  </label>
                </div>
                <p>
                  {campaign.trial_count} declared trials. Dataset{" "}
                  {campaign.dataset_id.slice(0, 12)}. Historical ranking is not
                  out-of-sample validation.
                </p>
                <Table
                  rows={campaign.ranking.map((r: Obj) => ({
                    ...r,
                    nav_return: r.total_return ?? r.raw_price_return,
                  }))}
                  columns={[
                    ["strategy", "Strategy"],
                    ["status", "Status"],
                    ["nav_return", "Raw NAV return (fraction)"],
                    ["sharpe", "Sharpe"],
                  ]}
                />
                <ul>
                  {campaign.limitations.map((l: string) => (
                    <li key={l}>{l}</li>
                  ))}
                </ul>
                <Download value={campaign} name="frontier-campaign.json">
                  Download campaign
                </Download>
              </section>
            )}
          </>
        )}
        {page === "Research" && (
          <ResearchPanel
            datasets={datasets}
            runs={runs}
            datasetId={datasetId}
            setDatasetId={setDatasetId}
            optIn={optIn}
            setOptIn={updateOptIn}
            busy={busy}
            request={api}
            work={work}
            notice={setNotice}
            error={setError}
            openStudy={openStudy}
          />
        )}
        {page === "Operations" && (
          <>
            <section className="wide-sheet">
              <h2>Runtime and capabilities</h2>
              <div className="capability-grid">
                <div>
                  <h3>Current service</h3>
                  <dl>
                    <dt>Engine</dt>
                    <dd>
                      {status?.engine?.name} {status?.engine?.version}
                    </dd>
                    <dt>Python</dt>
                    <dd>{status?.runtime?.python}</dd>
                    <dt>Workspace</dt>
                    <dd className="digest">{status?.workspace}</dd>
                    <dt>Datasets / studies</dt>
                    <dd>
                      {status?.dataset_count ?? "—"} /{" "}
                      {status?.run_count ?? "—"}
                    </dd>
                  </dl>
                </div>
                <div>
                  <h3>Evidence boundaries</h3>
                  {status?.capabilities &&
                    Object.entries(status.capabilities).map(([key, value]) => (
                      <div className="capability" key={key}>
                        <span>{key.replaceAll("_", " ")}</span>
                        <strong>
                          {typeof value === "boolean"
                            ? value
                              ? "Available"
                              : "Unsupported"
                            : String(value)}
                        </strong>
                      </div>
                    ))}
                </div>
              </div>
            </section>
            <section className="wide-sheet">
              <h2>Latest jobs</h2>
              <Table
                rows={runs.slice(0, 10)}
                columns={[
                  ["id", "Study"],
                  ["status", "Status"],
                  ["created_at", "Started (UTC)"],
                  ["error", "Error"],
                ]}
              />
            </section>
          </>
        )}
        {compared.length > 0 && page === "Study" && (
          <section className="wide-sheet comparison-inputs">
            <h2>Comparison inputs</h2>
            <Table
              rows={compared.map((r) => ({
                ...r.record.config,
                name: r.record.config.strategy.name,
                dataset: r.record.config.dataset_id,
              }))}
              columns={[
                ["name", "Strategy"],
                ["base_currency", "Currency"],
                ["initial_cash_usd", "Starting USD"],
                ["initial_cash_cad", "Starting CAD"],
                ["commission_per_order", "Fee / order"],
                ["slippage_bps", "Slippage bps"],
                ["dataset", "Dataset version"],
              ]}
            />
          </section>
        )}
        <footer>
          Frontier Research{" "}
          <span>
            Local snapshots. Explicit assumptions. Inspectable evidence.
          </span>
        </footer>
      </main>
    </div>
  );
}
createRoot(document.getElementById("root")!).render(<App />);
