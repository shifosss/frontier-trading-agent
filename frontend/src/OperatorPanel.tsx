import { useEffect, useState } from "react";
import { Table } from "./StudyDisplay";
import { number, percent, readable } from "./format";

type Amount = string | number;
type Decision = { symbol: string; action: string; reason: string };
type OperatorStatus = {
  mode: "paper";
  initialized: boolean;
  status:
    | "setup_required"
    | "ready"
    | "paused"
    | "recovery_required"
    | "risk_halted";
  message: string;
  account: null | {
    account_id: string;
    initial_cash_usd: number;
    last_snapshot: null | {
      account: { cash: Amount; equity: Amount; currency: string };
      positions: {
        symbol: string;
        qty: Amount;
        market_value: Amount;
        avg_entry_price: Amount;
      }[];
    };
    risk: null | {
      equity_cad: number;
      unit_nav: number;
      high_watermark: number;
      drawdown: number;
      halted: boolean;
    };
  };
  latest_cycle: null | {
    session: string;
    created_at: string;
    status: string;
    plan: {
      source_session: string;
      decision_at: string;
      eligible_at: string;
      expires_at: string;
      regime: string | { symbol: string; status: string; reason: string };
      decisions: Decision[];
      intents: unknown[];
    };
  };
  orders: {
    id: string;
    session: string;
    payload: {
      symbol: string;
      side: string;
      qty: Amount;
      type: string;
      limit_price?: Amount;
    };
    state: string;
    broker: null | {
      status: string;
      filled_qty: Amount;
      filled_avg_price: Amount | null;
    };
    error?: string;
  }[];
  requirements: string[];
};
type Props = {
  request: (path: string, body?: unknown) => Promise<any>;
  error: (message: string) => void;
};
const statusNames: Record<OperatorStatus["status"], string> = {
  setup_required: "Paper account setup needed",
  ready: "Local paper workflow ready",
  paused: "Paper workflow paused",
  recovery_required: "Reconciliation required",
  risk_halted: "Risk limit reached",
};
const amount = (value: Amount | null | undefined) =>
  value == null ? "Not yet observed" : number(Number(value));
const timestamp = (value: string) =>
  new Date(value).toISOString().slice(0, 19).replace("T", " ") + " UTC";

export default function OperatorPanel({ request, error }: Props) {
  const [state, setState] = useState<OperatorStatus | null>(null);
  const [loading, setLoading] = useState(true);
  async function refresh() {
    setLoading(true);
    try {
      setState(await request("/operator/status"));
    } catch (failure) {
      error((failure as Error).message);
    } finally {
      setLoading(false);
    }
  }
  useEffect(() => {
    void refresh();
  }, [request, error]);
  const snapshot = state?.account?.last_snapshot;
  const risk = state?.account?.risk;
  const cycle = state?.latest_cycle;
  return (
    <div className="operator">
      <section className="wide-sheet">
        <div className="section-heading">
          <div>
            <h2>Daily monitoring. Weekly entries.</h2>
            <p>US stocks · cash only · paper execution validation</p>
          </div>
          <button
            className="secondary compact"
            disabled={loading}
            onClick={() => void refresh()}
          >
            {loading ? "Loading status…" : "Refresh desk"}
          </button>
        </div>
        {state && (
          <div
            className={`operator-state ${state.status === "risk_halted" || state.status === "recovery_required" ? "operator-attention" : ""}`}
            role="status"
          >
            <span className="badge synthetic">Paper only</span>
            <h3>{statusNames[state.status]}</h3>
            <p>{state.message}</p>
          </div>
        )}
        <p className="operator-copy">
          This desk shows saved paper-account activity. Refreshing does not
          contact the broker or run a trading cycle. Live capital and options
          are not enabled.
        </p>
      </section>
      {state && (
        <>
          <section
            className="operator-pipeline"
            aria-label="Paper trading workflow"
          >
            <article>
              <span>01 · Account</span>
              <h3>
                {snapshot ? "Snapshot recorded" : "Awaiting first snapshot"}
              </h3>
              <p>
                {state.initialized
                  ? "Dedicated paper account configured locally."
                  : "Set up a dedicated paper account first."}
              </p>
            </article>
            <article>
              <span>02 · Daily review</span>
              <h3>{cycle ? readable(cycle.status) : "No cycle recorded"}</h3>
              <p>
                {cycle
                  ? `Latest session: ${cycle.session}`
                  : "A cycle checks holdings, signals and risk before proposing orders."}
              </p>
            </article>
            <article>
              <span>03 · Paper orders</span>
              <h3>{state.orders.length} orders tracked</h3>
              <p>
                {cycle
                  ? `${cycle.plan.intents.length} intents in the latest plan. Broker acknowledgements appear below.`
                  : "Submitted orders and their outcomes will be recorded here."}
              </p>
            </article>
          </section>
          {state.status === "setup_required" && (
            <section className="wide-sheet operator-setup">
              <h2>Connect the paper proving ground</h2>
              <p>
                Use a dedicated Alpaca paper account. Its simulated USD cash
                must match the amount you initialize here. No live broker
                connection has been established.
              </p>
              <ol>
                <li>
                  Create or reset a dedicated paper account with the intended
                  simulated cash.
                </li>
                <li>
                  Configure <code>FRONTIER_ALPACA_PAPER_KEY</code> and{" "}
                  <code>FRONTIER_ALPACA_PAPER_SECRET</code> locally. Never paste
                  credentials into this conversation.
                </li>
                <li>Initialize the account, then run the first paper cycle.</li>
              </ol>
              <details>
                <summary>Local setup commands</summary>
                <pre>
                  {
                    "frontier paper-init --account-id <paper-account-id> --cash-usd <simulated-USD-cash>\nfrontier paper-cycle"
                  }
                </pre>
                <p>
                  Use the paper account ID and its matching simulated USD
                  balance. These commands belong in the local project terminal.
                </p>
              </details>
            </section>
          )}
          <section className="wide-sheet">
            <div className="section-heading">
              <div>
                <h2>Saved account and risk</h2>
                <p>
                  {state.account
                    ? `Paper account ${state.account.account_id}`
                    : "No account initialized"}
                </p>
              </div>
              <span
                className={`badge ${risk?.halted ? "failed" : "synthetic"}`}
              >
                {risk
                  ? risk.halted
                    ? "Risk halt active"
                    : "Risk snapshot recorded"
                  : "Awaiting risk snapshot"}
              </span>
            </div>
            <div className="metric-strip">
              <div>
                <span>Paper cash · {snapshot?.account.currency ?? "USD"}</span>
                <strong>{amount(snapshot?.account.cash)}</strong>
              </div>
              <div>
                <span>
                  Paper equity · {snapshot?.account.currency ?? "USD"}
                </span>
                <strong>{amount(snapshot?.account.equity)}</strong>
              </div>
              <div>
                <span>Equity in CAD</span>
                <strong>
                  {risk ? number(risk.equity_cad) : "Not yet observed"}
                </strong>
              </div>
              <div>
                <span>Recorded drawdown</span>
                <strong>
                  {risk ? percent(risk.drawdown) : "Not yet observed"}
                </strong>
              </div>
            </div>
            {state.account && (
              <p className="operator-copy">
                Initialized with {number(state.account.initial_cash_usd)}{" "}
                simulated USD.{" "}
                {risk && (
                  <>
                    Unit NAV {number(risk.unit_nav, 4)}; high-water mark{" "}
                    {number(risk.high_watermark, 4)}.{" "}
                  </>
                )}
                Recorded balances are not live quotes.
              </p>
            )}
            <div className="operator-table-heading">
              <h3>Paper holdings</h3>
            </div>
            {snapshot?.positions.length ? (
              <Table
                rows={snapshot.positions.map((position) => ({
                  symbol: position.symbol,
                  shares: String(position.qty),
                  basis: amount(position.avg_entry_price),
                  value: amount(position.market_value),
                }))}
                columns={[
                  ["symbol", "Symbol"],
                  ["shares", "Shares"],
                  ["basis", "Average entry · USD"],
                  ["value", "Market value · USD"],
                ]}
              />
            ) : (
              <p className="empty-small">
                {snapshot
                  ? "No positions in the saved account snapshot."
                  : "Holdings will appear after a broker snapshot is recorded."}
              </p>
            )}
          </section>
          <section className="wide-sheet operator-decisions">
            <div className="section-heading">
              <div>
                <h2>Latest daily decision</h2>
                <p>
                  {cycle
                    ? `Recorded ${timestamp(cycle.created_at)}`
                    : "No decision saved yet"}
                </p>
              </div>
            </div>
            {cycle ? (
              <>
                <p className="operator-copy">
                  Source session {cycle.plan.source_session}. Eligible{" "}
                  {timestamp(cycle.plan.eligible_at)}; expires{" "}
                  {timestamp(cycle.plan.expires_at)}. Regime:{" "}
                  {typeof cycle.plan.regime === "string"
                    ? readable(cycle.plan.regime)
                    : `${cycle.plan.regime.symbol} ${readable(cycle.plan.regime.status)} — ${cycle.plan.regime.reason}`}
                  .
                </p>
                {cycle.plan.decisions.length ? (
                  <Table
                    rows={cycle.plan.decisions.map((decision) => ({
                      ...decision,
                      action: readable(decision.action),
                    }))}
                    columns={[
                      ["symbol", "Symbol"],
                      ["action", "Decision"],
                      ["reason", "Reason"],
                    ]}
                  />
                ) : (
                  <p className="empty-small">
                    The latest cycle recorded no symbol decisions.
                  </p>
                )}
              </>
            ) : (
              <p className="empty-small">
                Each paper cycle records its decision and reason, including
                waiting or holding cash.
              </p>
            )}
          </section>
          <section className="wide-sheet operator-orders">
            <div className="section-heading">
              <div>
                <h2>Paper orders and outcomes</h2>
                <p>Saved submission state and broker acknowledgements.</p>
              </div>
            </div>
            {state.orders.length ? (
              <Table
                rows={state.orders.map((order) => ({
                  id: order.id,
                  session: order.session,
                  symbol: order.payload.symbol,
                  side: order.payload.side,
                  qty: String(order.payload.qty),
                  type:
                    order.payload.type +
                    (order.payload.limit_price == null
                      ? ""
                      : ` at ${amount(order.payload.limit_price)} USD`),
                  state: readable(order.state),
                  broker: order.broker
                    ? readable(order.broker.status)
                    : "No saved broker status",
                  fills: order.broker
                    ? `${order.broker.filled_qty} at ${order.broker.filled_avg_price == null ? "—" : amount(order.broker.filled_avg_price) + " USD"}`
                    : "—",
                  error: order.error ?? "—",
                }))}
                columns={[
                  ["session", "Session"],
                  ["symbol", "Symbol"],
                  ["side", "Side"],
                  ["qty", "Shares"],
                  ["type", "Order"],
                  ["state", "Local state"],
                  ["broker", "Broker state"],
                  ["fills", "Filled"],
                  ["error", "Issue"],
                  ["id", "Order ID"],
                ]}
              />
            ) : (
              <p className="empty-small">
                No paper orders recorded. A signal or order intent is not a
                submitted or filled order.
              </p>
            )}
          </section>
          {state.requirements.length > 0 && (
            <section className="wide-sheet operator-requirements">
              <h2>What needs attention</h2>
              <ul>
                {state.requirements.map((requirement) => (
                  <li key={requirement}>{requirement}</li>
                ))}
              </ul>
            </section>
          )}
        </>
      )}
    </div>
  );
}
