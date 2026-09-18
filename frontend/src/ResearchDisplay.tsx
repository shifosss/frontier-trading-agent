import { ratio, readable, savedText } from "./format";

export type ResearchAttempt = {
  number: number;
  status: string;
  created_at?: string;
  error?: string;
  reasons?: string[];
  run_id?: string;
  proposal?: {
    name?: unknown;
    economic_mechanism?: unknown;
    failure_condition?: unknown;
    family?: unknown;
    lookback?: unknown;
    rebalance_every?: unknown;
    max_weight?: unknown;
    required_inputs?: unknown;
  };
  feedback?: {
    total_return?: number | null;
    raw_price_return?: number | null;
    max_drawdown?: number | null;
    trade_count?: number;
    fees?: { USD?: number; CAD?: number };
  };
  provider?: {
    requested_model?: string;
    elapsed_seconds?: number;
    usage?: Record<string, unknown>;
  };
};

export function SavedJson({ value }: { value: unknown }) {
  return (
    <details className="saved-json">
      <summary>Inspect saved record</summary>
      <pre>{JSON.stringify(value, null, 2)}</pre>
    </details>
  );
}
export function ProposalAttempt({
  attempt,
  busy,
  onInspect,
}: {
  attempt: ResearchAttempt;
  busy: boolean;
  onInspect: (id: string) => Promise<void>;
}) {
  const runId = attempt.run_id;
  return (
    <article className="proposal-attempt">
      <div className="section-heading">
        <div>
          <h3>
            Attempt {attempt.number}
            {attempt.proposal?.name ? `: ${attempt.proposal.name}` : ""}
          </h3>
          <p>{attempt.created_at?.slice(0, 19).replace("T", " ")} UTC</p>
        </div>
        <span
          className={`badge ${["provider_failed", "evaluation_failed", "rejected"].includes(attempt.status) ? "failed" : ""}`}
        >
          {readable(attempt.status)}
        </span>
      </div>
      {attempt.error && <p className="attempt-error">{attempt.error}</p>}
      {attempt.reasons && attempt.reasons.length > 0 && (
        <ul className="attempt-error">
          {attempt.reasons.map((reason: string) => (
            <li key={reason}>{reason}</li>
          ))}
        </ul>
      )}
      {attempt.proposal && (
        <div className="proposal-body">
          <div>
            <h4>Proposed mechanism</h4>
            <p>{savedText(attempt.proposal.economic_mechanism)}</p>
            <h4>Failure condition</h4>
            <p>{savedText(attempt.proposal.failure_condition)}</p>
          </div>
          <dl>
            <dt>Rule</dt>
            <dd>{readable(attempt.proposal.family)}</dd>
            <dt>Lookback</dt>
            <dd>{savedText(attempt.proposal.lookback)} bars</dd>
            <dt>Rebalance</dt>
            <dd>Every {savedText(attempt.proposal.rebalance_every)} bars</dd>
            <dt>Max group weight</dt>
            <dd>{ratio(attempt.proposal.max_weight)}</dd>
            <dt>Required inputs</dt>
            <dd>
              {Array.isArray(attempt.proposal.required_inputs)
                ? attempt.proposal.required_inputs.map(readable).join(", ")
                : savedText(attempt.proposal.required_inputs)}
            </dd>
          </dl>
        </div>
      )}
      {attempt.feedback && (
        <div className="attempt-feedback">
          <div>
            <span>
              {attempt.feedback.total_return == null
                ? "Simulated raw-price return"
                : "Replay return"}
            </span>
            <strong>
              {ratio(
                attempt.feedback.total_return ??
                  attempt.feedback.raw_price_return,
              )}
            </strong>
          </div>
          <div>
            <span>Max drawdown</span>
            <strong>{ratio(attempt.feedback.max_drawdown)}</strong>
          </div>
          <div>
            <span>Fills</span>
            <strong>{attempt.feedback.trade_count ?? "Not available"}</strong>
          </div>
          <div>
            <span>Native fees</span>
            <strong>
              {attempt.feedback.fees?.USD ?? "—"} USD /{" "}
              {attempt.feedback.fees?.CAD ?? "—"} CAD
            </strong>
          </div>
        </div>
      )}
      <div className="attempt-actions">
        {runId && (
          <button
            className="text-button"
            disabled={busy}
            onClick={() => onInspect(runId)}
          >
            Inspect replay
          </button>
        )}
        {attempt.provider && (
          <span>
            Model {attempt.provider.requested_model ?? "Not reported"};{" "}
            {typeof attempt.provider.elapsed_seconds === "number"
              ? `${attempt.provider.elapsed_seconds.toFixed(1)}s`
              : "Time not reported"}
          </span>
        )}
      </div>
      {attempt.provider?.usage && (
        <details className="usage-details">
          <summary>Recorded model usage</summary>
          <dl>
            {Object.entries(attempt.provider.usage).map(([key, value]) => (
              <div key={key}>
                <dt>{readable(key)}</dt>
                <dd>
                  {typeof value === "object"
                    ? JSON.stringify(value)
                    : String(value)}
                </dd>
              </div>
            ))}
          </dl>
          <p>
            Recorded usage is shown as returned. No dollar cost is inferred.
          </p>
        </details>
      )}
      <SavedJson value={attempt} />
    </article>
  );
}
