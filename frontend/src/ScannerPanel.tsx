import { useEffect, useState } from "react";
import { Download } from "./StudyDisplay";
import { day, number, percent } from "./format";

type Currency = "USD" | "CAD";
type Candidate = {
  symbol: string;
  name: string;
  currency: Currency;
  group: string;
  asset_type: string;
  status: "selected" | "eligible" | "excluded";
  reasons: string[];
  last_session: string | null;
  expected_session: string;
  price: number | null;
  momentum_20: number | null;
  momentum_60: number | null;
  annualized_volatility: number | null;
  average_dollar_volume_20: number | null;
  score: number | null;
  rank: number | null;
  quantity: number;
  estimated_notional: number;
  estimated_cost: number;
  allocation_fraction: number;
  sizing_reason: string | null;
};
type DiagnosticSummary = {
  status?: string;
  reason?: string;
  total_cohort_count?: number;
  incomplete_cohort_count?: number;
  cohort_count: number;
  paired_cohort_count: number;
  candidate_count: number;
  mean_return: number | null;
  median_return: number | null;
  win_rate: number | null;
  mean_benchmark_return: number | null;
  mean_excess_return: number | null;
  mean_stressed_return: number | null;
};
type ScanArtifact = {
  scan_id: string;
  created_at: string;
  source: {
    name: string;
    as_of: string;
    capture_id: string;
    succeeded: number;
    failed: { symbol: string; error: string }[];
    cached: boolean;
  };
  scan: {
    as_of: string;
    status: "watchlist" | "no_trade";
    universe_size: number;
    rows: Candidate[];
    selected: Candidate[];
    cash_by_currency: Record<Currency, number>;
    unallocated_cash: Record<Currency, number>;
    limitations: string[];
  };
  study: {
    policy: {
      diagnostic_holding_sessions: number;
      diagnostic_entry: string;
      diagnostic_round_trip_cost_bps: number;
      diagnostic_stressed_cost_bps: number;
    };
    summary: Record<Currency, DiagnosticSummary>;
    limitations: string[];
  };
  funding?: {
    mode: "existing_cash" | "planned_cad_to_usd";
    cash_before: Record<Currency, number>;
    cash_after: Record<Currency, number>;
    convert_cad: number;
    estimated_fee_cad: number;
    estimated_usd_credit: number;
    reference: {
      usd_cad: number;
      event_time: string;
      available_at: string;
      source_url: string;
    } | null;
    limitations: string[];
  };
  readiness: { status: string; reasons: string[] };
};
type Props = {
  busy: string;
  request: (path: string, body?: unknown) => Promise<any>;
  work: (name: string, fn: () => Promise<void>) => Promise<void>;
  notice: (message: string) => void;
  error: (message: string) => void;
};
const currencies: Currency[] = ["USD", "CAD"];
const rate = (value: number | null) => (value == null ? "—" : percent(value));

function CandidateTable({ rows }: { rows: Candidate[] }) {
  return (
    <div className="table-scroll">
      <table className="scanner-table">
        <thead>
          <tr>
            <th>Candidate / decision</th>
            <th>Last close</th>
            <th>Rule score</th>
            <th>20 / 60 session trend</th>
            <th>Annualized volatility</th>
            <th>Simulated shares / outlay</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.symbol}>
              <td>
                <strong>{row.symbol}</strong>
                <small>{row.name}</small>
                <span
                  className={`badge ${row.status === "excluded" ? "synthetic" : ""}`}
                >
                  {row.status === "selected"
                    ? "In simulated basket"
                    : row.status}
                </span>
                <details>
                  <summary>Why this decision</summary>
                  <ul>
                    {row.reasons.map((reason) => (
                      <li key={reason}>{reason}</li>
                    ))}
                  </ul>
                  {row.sizing_reason && <p>{row.sizing_reason}</p>}
                  <p>
                    Exposure group: {row.group}. Average daily turnover:{" "}
                    {number(row.average_dollar_volume_20, 0)} {row.currency}.
                  </p>
                </details>
              </td>
              <td>
                {row.price == null ? "—" : number(row.price)} {row.currency}
                <small>{row.last_session ?? "No available session"}</small>
              </td>
              <td>
                {row.score == null ? "—" : number(row.score, 3)}
                <small>
                  {row.rank == null ? "Not ranked" : `Rank ${row.rank}`}
                </small>
              </td>
              <td>
                {rate(row.momentum_20)} / {rate(row.momentum_60)}
              </td>
              <td>{rate(row.annualized_volatility)}</td>
              <td>
                {number(row.quantity, 0)} shares
                <small>
                  {number(row.estimated_notional + row.estimated_cost)}{" "}
                  {row.currency} including estimated costs
                </small>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default function ScannerPanel({
  busy,
  request,
  work,
  notice,
  error,
}: Props) {
  const [scans, setScans] = useState<ScanArtifact[]>([]);
  const [selectedId, setSelectedId] = useState("");
  const [cashUSD, setCashUSD] = useState(0);
  const [cashCAD, setCashCAD] = useState(700);
  const [convertCAD, setConvertCAD] = useState(0);
  const [loading, setLoading] = useState(true);
  const active = scans.find((scan) => scan.scan_id === selectedId);
  useEffect(() => {
    if (!active) return;
    const cash = active.funding?.cash_before ?? active.scan.cash_by_currency;
    setCashCAD(cash.CAD);
    setCashUSD(cash.USD);
    setConvertCAD(active.funding?.convert_cad ?? 0);
  }, [active]);
  useEffect(() => {
    let mounted = true;
    request("/scans")
      .then((saved: ScanArtifact[]) => {
        if (!mounted) return;
        setScans(saved);
        setSelectedId(saved[0]?.scan_id ?? "");
      })
      .catch((e: Error) => {
        if (mounted) error(e.message);
      })
      .finally(() => {
        if (mounted) setLoading(false);
      });
    return () => {
      mounted = false;
    };
  }, [request, error]);
  function runScan() {
    return work("Scanning US and Canadian markets", async () => {
      const result: ScanArtifact = await request("/scans", {
        refresh: true,
        initial_cash_usd: cashUSD,
        initial_cash_cad: cashCAD,
        convert_cad: convertCAD,
      });
      setScans((saved) => [result, ...saved]);
      setSelectedId(result.scan_id);
      notice(
        "Market scan and historical diagnostics are saved. The basket uses simulated cash; no orders were sent.",
      );
    });
  }
  return (
    <div className="scanner">
      <section className="wide-sheet scan-control">
        <div className="section-heading">
          <div>
            <h2>Your market shortlist</h2>
            <p>
              Stock candidates from a declared US and Canadian universe, ranked
              from completed daily sessions.
            </p>
          </div>
          <span className="badge synthetic">
            Research shortlist · simulated basket
          </span>
        </div>
        <form
          className="scan-form"
          onSubmit={(event) => {
            event.preventDefault();
            void runScan();
          }}
        >
          <label>
            Simulated USD cash
            <input
              type="number"
              min="0"
              step="0.01"
              required
              value={cashUSD}
              onChange={(event) => setCashUSD(Number(event.target.value))}
            />
          </label>
          <label>
            Simulated CAD cash
            <input
              type="number"
              min="0"
              step="0.01"
              required
              value={cashCAD}
              onChange={(event) => setCashCAD(Number(event.target.value))}
            />
          </label>
          <label>
            CAD to convert (simulation)
            <input
              type="number"
              min="0"
              max={cashCAD}
              step="0.01"
              required
              value={convertCAD}
              onChange={(event) => setConvertCAD(Number(event.target.value))}
            />
          </label>
          <button
            className="primary"
            type="submit"
            disabled={!!busy || loading}
          >
            Run market scan
          </button>
        </form>
        <p className="scan-copy">
          CAD 700 illustrates a first monthly contribution within your CAD
          600–800 plan; it is not reconciled account cash. Your long-term ETF
          holdings and contributions stay separate. Enter balances before any
          planned conversion. You can model CAD-to-USD funding using the latest
          published reference rate and Wealthsimple conversion fees (1.5% below
          CAD 10,000); the result assumes USD is retained in a USD account
          between trades. Actual conversion is not performed. Option selection
          is not yet qualified.
        </p>
      </section>
      {loading ? (
        <p className="empty-small" role="status">
          Loading saved scans…
        </p>
      ) : !active ? (
        <section className="wide-sheet scan-empty">
          <h2>Find candidates, then examine the evidence</h2>
          <p>
            Run a scan to retrieve free market data, rank eligible stocks, use
            ETFs as benchmarks, and inspect how the fixed rule performed on
            earlier dates. Instruments with stale or incomplete data remain
            visible with the reason they were excluded.
          </p>
        </section>
      ) : (
        <>
          <div className="scan-history">
            <label>
              Saved market scan
              <select
                value={selectedId}
                onChange={(event) => setSelectedId(event.target.value)}
              >
                {scans.map((scan) => (
                  <option key={scan.scan_id} value={scan.scan_id}>
                    {scan.created_at.slice(0, 19).replace("T", " ")} UTC ·{" "}
                    {scan.scan.selected.length} candidates ·{" "}
                    {scan.funding?.mode === "planned_cad_to_usd"
                      ? "USD conversion scenario"
                      : "Native cash"}
                  </option>
                ))}
              </select>
            </label>
            <Download
              value={active}
              name={`frontier-scan-${active.scan_id}.json`}
            >
              Download scan and evidence
            </Download>
          </div>
          {active.funding?.mode === "planned_cad_to_usd" && (
            <section className="wide-sheet">
              <div className="section-heading">
                <div>
                  <h2>Simulated CAD-to-USD funding</h2>
                  <p>One conversion into a retained USD cash balance.</p>
                </div>
                <span className="badge synthetic">Reference estimate</span>
              </div>
              <p className="scan-copy">
                CAD {number(active.funding.convert_cad)} debited once →
                approximately USD {number(active.funding.estimated_usd_credit)}{" "}
                credited, including an estimated CAD{" "}
                {number(active.funding.estimated_fee_cad)} conversion fee,
                before broker spread and account charges.
                {active.funding.reference && (
                  <>
                    {" "}
                    Reference: {number(active.funding.reference.usd_cad, 4)} CAD
                    per USD, published{" "}
                    {day(active.funding.reference.available_at)}.
                  </>
                )}{" "}
                The cash balances below are after this simulated conversion.
              </p>
              <details className="scan-details">
                <summary>Conversion assumptions and excluded costs</summary>
                <ul>
                  {active.funding.limitations.map((limit) => (
                    <li key={limit}>{limit}</li>
                  ))}
                </ul>
              </details>
            </section>
          )}
          <section className="wide-sheet">
            <div className="section-heading">
              <div>
                <h2>
                  {active.scan.status === "no_trade"
                    ? "No basket fits these constraints"
                    : "Current simulated basket"}
                </h2>
                <p>
                  {active.source.succeeded} / {active.scan.universe_size}{" "}
                  instruments retrieved · {active.source.name}
                  {active.source.cached ? " · saved capture" : ""}
                </p>
              </div>
              <div className="scan-asof">
                <strong>As of {day(active.scan.as_of)}</strong>
                <small>
                  Capture {active.source.as_of.slice(0, 19).replace("T", " ")}{" "}
                  UTC
                </small>
              </div>
            </div>
            <p className="scan-copy">
              Stocks are eligible for the simulated basket; ETFs provide
              benchmark context. Scores rank momentum against volatility under
              one fixed rule. They are not expected returns or a probability of
              profit. Each row shows the last completed session used; estimates
              use that closing price.
            </p>
            <div className="scan-cash">
              {currencies.map((currency) => (
                <div key={currency}>
                  <span>{currency} simulated cash</span>
                  <strong>
                    {number(active.scan.cash_by_currency[currency])}
                  </strong>
                  <small>
                    {number(active.scan.unallocated_cash[currency])} left
                    unallocated
                  </small>
                </div>
              ))}
            </div>
            {active.scan.selected.length ? (
              <CandidateTable rows={active.scan.selected} />
            ) : (
              <p className="empty-small">
                Keep the simulated allocation in cash. Inspect the exclusions
                below to see which requirements were not met.
              </p>
            )}
          </section>
          <section className="wide-sheet">
            <div className="section-heading">
              <div>
                <h2>Did this rule beat its benchmark?</h2>
                <p>
                  {active.study.policy.diagnostic_holding_sessions}-session
                  forward returns, with {active.study.policy.diagnostic_entry}{" "}
                  entry.
                </p>
              </div>
              <span className="badge synthetic">Exploratory evidence</span>
            </div>
            <div className="scan-diagnostics">
              {currencies.map((currency) => {
                const result = active.study.summary[currency];
                return (
                  <article key={currency}>
                    <h3>{currency} candidates</h3>
                    <p>
                      {result.cohort_count} historical baskets ·{" "}
                      {result.candidate_count} candidate observations
                      <br />
                      {result.paired_cohort_count} baskets matched to a
                      benchmark
                    </p>
                    {result.reason && <p>{result.reason}</p>}
                    {!!result.incomplete_cohort_count && (
                      <p>
                        {result.incomplete_cohort_count} periods excluded for
                        incomplete data.
                      </p>
                    )}
                    <dl>
                      <dt>Mean net forward return</dt>
                      <dd>{rate(result.mean_return)}</dd>
                      <dt>Benchmark mean return</dt>
                      <dd>{rate(result.mean_benchmark_return)}</dd>
                      <dt>Mean excess over benchmark</dt>
                      <dd>{rate(result.mean_excess_return)}</dd>
                      <dt>Mean with stressed costs</dt>
                      <dd>{rate(result.mean_stressed_return)}</dd>
                      <dt>Median net return</dt>
                      <dd>{rate(result.median_return)}</dd>
                      <dt>Positive-return baskets</dt>
                      <dd>{rate(result.win_rate)}</dd>
                    </dl>
                    <p className="scan-verdict">
                      {result.status === "unfunded"
                        ? "No simulated cash in this currency; no funded comparison was run."
                        : result.mean_excess_return == null
                          ? "Too few usable outcomes to compare this rule."
                          : result.mean_excess_return > 0
                            ? "The historical average exceeded its benchmark. This remains unvalidated for future trading."
                            : "The historical average did not beat its benchmark. This study does not establish a reason to prefer this rule."}
                    </p>
                  </article>
                );
              })}
            </div>
            <p className="scan-copy">
              Each historical basket is a separate forward observation, not a
              compounded portfolio. These averages are not annualized. Cash
              earns 0% in this comparison.{" "}
              {active.funding?.mode === "planned_cad_to_usd" &&
                "USD cohort returns exclude CAD/USD valuation changes, conversion fees and account charges. "}{" "}
              Estimated round-trip costs are{" "}
              {active.study.policy.diagnostic_round_trip_cost_bps} bps, rising
              to {active.study.policy.diagnostic_stressed_cost_bps} bps in the
              stress case.
            </p>
            <details className="scan-details">
              <summary>Study method and limits</summary>
              <ul>
                {active.study.limitations.map((limit) => (
                  <li key={limit}>{limit}</li>
                ))}
              </ul>
            </details>
          </section>
          <section className="wide-sheet">
            <div className="section-heading">
              <div>
                <h2>Every instrument, every decision</h2>
                <p>
                  {
                    active.scan.rows.filter((row) => row.status === "excluded")
                      .length
                  }{" "}
                  excluded ·{" "}
                  {
                    active.scan.rows.filter((row) => row.status === "eligible")
                      .length
                  }{" "}
                  eligible but outside the sized basket
                </p>
              </div>
            </div>
            <details className="scan-universe">
              <summary>
                Inspect all {active.scan.rows.length} instruments
              </summary>
              <CandidateTable rows={active.scan.rows} />
            </details>
            {active.source.failed.length > 0 && (
              <details className="scan-details">
                <summary>
                  Data unavailable for {active.source.failed.length} instruments
                </summary>
                <ul>
                  {active.source.failed.map((failure) => (
                    <li key={failure.symbol}>
                      <strong>{failure.symbol}:</strong> {failure.error}
                    </li>
                  ))}
                </ul>
              </details>
            )}
          </section>
          <section className="wide-sheet scan-readiness">
            <h2>Before this becomes an allocation</h2>
            <p className="scan-mandate">
              Cash account only. Your stated maximum drawdown is 30%; it is not
              an enforced loss limit without account monitoring and execution
              controls.
            </p>
            <ul>
              {active.readiness.reasons.map((reason) => (
                <li key={reason}>{reason}</li>
              ))}
            </ul>
            <details>
              <summary>Scan assumptions and limitations</summary>
              <ul>
                {active.scan.limitations.map((limit) => (
                  <li key={limit}>{limit}</li>
                ))}
              </ul>
            </details>
          </section>
        </>
      )}
    </div>
  );
}
