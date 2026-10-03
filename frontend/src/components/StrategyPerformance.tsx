import type { StrategyPerf } from "../api";

type Props = { rows: StrategyPerf[] };

export function StrategyPerformance({ rows }: Props) {
  if (!rows.length) {
    return (
      <p className="empty">
        No learning data yet. Run recoveries — Agent 5 writes rates here for Agent 3.
      </p>
    );
  }

  return (
    <div className="table-wrap">
      <table>
        <thead>
          <tr>
            <th>Strategy</th>
            <th>Failure</th>
            <th>Attempts</th>
            <th>Wins</th>
            <th>Rate</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={`${r.strategy}-${r.failure_type}`}>
              <td className="mono">{r.strategy}</td>
              <td className="mono">{r.failure_type}</td>
              <td>{r.attempts}</td>
              <td>{r.successes}</td>
              <td>
                <strong>{Math.round(r.recovery_rate * 100)}%</strong>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
