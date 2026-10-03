import {
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { Funnel } from "../api";
import { formatInr } from "../api";

type Props = { data: Funnel | null };

export function RecoveryFunnel({ data }: Props) {
  if (!data) return <p className="loading">Loading funnel…</p>;

  const chart = [
    { stage: "Failures", count: data.failures },
    { stage: "Attempted", count: data.attempted },
    { stage: "Recovered", count: data.recovered },
    { stage: "Escalated", count: data.escalated },
  ];

  return (
    <>
      <div className="funnel-stats">
        <div className="stat">
          <div className="label">Revenue recovered</div>
          <div className="value">{formatInr(data.revenue_saved_paise)}</div>
        </div>
        <div className="stat">
          <div className="label">Recovery rate</div>
          <div className="value">
            {data.attempted
              ? `${Math.round((data.recovered / data.attempted) * 100)}%`
              : "—"}
          </div>
        </div>
      </div>
      <div className="chart-box">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={chart} margin={{ top: 8, right: 8, left: -12, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.08)" />
            <XAxis dataKey="stage" tick={{ fontSize: 12, fill: "#9aa3ad" }} />
            <YAxis allowDecimals={false} tick={{ fontSize: 12, fill: "#9aa3ad" }} />
            <Tooltip
              contentStyle={{
                background: "#12151a",
                border: "1px solid rgba(255,255,255,0.1)",
                borderRadius: 8,
              }}
            />
            <Bar dataKey="count" fill="#2a7fff" radius={[6, 6, 0, 0]} />
          </BarChart>
        </ResponsiveContainer>
      </div>
    </>
  );
}
