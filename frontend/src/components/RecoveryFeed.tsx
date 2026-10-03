import type { RecoveryRun } from "../api";
import { formatInr } from "../api";

type Props = {
  rows: RecoveryRun[];
  selectedId: string | null;
  onSelect: (id: string) => void;
};

export function RecoveryFeed({ rows, selectedId, onSelect }: Props) {
  if (!rows.length) {
    return <p className="empty">No recovery runs yet. POST a failed payment to seed the feed.</p>;
  }

  return (
    <div className="table-wrap">
      <table>
        <thead>
          <tr>
            <th>Payment</th>
            <th>Amount</th>
            <th>Failure</th>
            <th>Strategy</th>
            <th>Status</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr
              key={r.id}
              className={`clickable ${selectedId === r.id ? "active" : ""}`}
              onClick={() => onSelect(r.id)}
            >
              <td>
                <div className="mono">{r.payment_id}</div>
                <div className="mono" style={{ color: "var(--muted)", marginTop: 2 }}>
                  {r.payment_method ?? "—"}
                </div>
              </td>
              <td>{formatInr(r.amount_paise)}</td>
              <td className="mono">{r.failure_type ?? "—"}</td>
              <td className="mono">{r.strategy ?? "—"}</td>
              <td>
                <span className={`status ${r.status}`}>{r.status}</span>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
