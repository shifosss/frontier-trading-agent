import type { ReactNode } from "react";
import { day, number } from "./format";

type EquityPoint = { timestamp: string; nav: number };

export function Download({
  value,
  name,
  children,
}: {
  value: unknown;
  name: string;
  children: ReactNode;
}) {
  return (
    <button
      className="text-button"
      onClick={() => {
        const u = URL.createObjectURL(
          new Blob([JSON.stringify(value, null, 2)], {
            type: "application/json",
          }),
        );
        const a = document.createElement("a");
        a.href = u;
        a.download = name;
        a.click();
        URL.revokeObjectURL(u);
      }}
    >
      {children}
    </button>
  );
}
export function Table({
  rows,
  columns,
}: {
  rows: Record<string, unknown>[];
  columns: [string, string][];
}) {
  return rows.length ? (
    <div className="table-scroll">
      <table>
        <thead>
          <tr>
            {columns.map(([key, title]) => (
              <th key={key}>{title}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={i}>
              {columns.map(([key]) => (
                <td key={key}>
                  {typeof r[key] === "number"
                    ? number(r[key], 4)
                    : String(r[key] ?? "—")}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  ) : (
    <p className="empty-small">No records for this study.</p>
  );
}
export function EquityChart({
  series,
  currency,
}: {
  series: { name: string; points: EquityPoint[]; color: string }[];
  currency: string;
}) {
  const all = series.flatMap((s) => s.points);
  if (!all.length)
    return (
      <div className="chart-empty">
        <div className="empty-plot" aria-hidden="true" />
        <h3>Your first study starts here</h3>
        <p>
          Select a dataset and run a study to inspect actual equity,
          <br />
          decisions and fills from the replay engine.
        </p>
        <span>No result has been generated.</span>
      </div>
    );
  const minTime = Math.min(...all.map((p) => Date.parse(p.timestamp)));
  const maxTime = Math.max(...all.map((p) => Date.parse(p.timestamp)));
  let low = Math.min(...all.map((p) => p.nav)),
    high = Math.max(...all.map((p) => p.nav));
  const pad = (high - low) * 0.12 || Math.max(high * 0.005, 1);
  low -= pad;
  high += pad;
  const x = (p: EquityPoint) =>
    70 + ((Date.parse(p.timestamp) - minTime) / (maxTime - minTime || 1)) * 830;
  const y = (v: number) => 260 - ((v - low) / (high - low)) * 215;
  return (
    <>
      <div className="chart-legend">
        {series.map((s) => (
          <span key={s.name}>
            <i style={{ background: s.color }} />
            {s.name}
          </span>
        ))}
      </div>
      <svg
        role="img"
        aria-label={`Equity curve in ${currency}, from ${day(new Date(minTime).toISOString())} to ${day(new Date(maxTime).toISOString())}`}
        viewBox="0 0 930 310"
        className="equity-chart"
      >
        {Array.from({ length: 5 }, (_, i) => {
          const v = low + ((high - low) * i) / 4;
          return (
            <g key={i}>
              <line x1="70" x2="900" y1={y(v)} y2={y(v)} stroke="#e5edf5" />
              <text x="59" y={y(v) + 4} textAnchor="end">
                {number(v, 0)}
              </text>
            </g>
          );
        })}
        {series.map((s) => (
          <polyline
            key={s.name}
            points={s.points.map((p) => `${x(p)},${y(p.nav)}`).join(" ")}
            fill="none"
            stroke={s.color}
            strokeWidth="2.5"
            strokeLinejoin="round"
          />
        ))}
        {[0, 0.5, 1].map((v, i) => (
          <text
            key={i}
            x={70 + 830 * v}
            y="293"
            textAnchor={v === 0 ? "start" : v === 1 ? "end" : "middle"}
          >
            {day(new Date(minTime + (maxTime - minTime) * v).toISOString())}
          </text>
        ))}
      </svg>
    </>
  );
}
