import { useEffect, useState } from "react";
import { api, formatInr, type TraceResponse } from "../api";

type Props = { runId: string | null };

const AGENT_LABEL: Record<string, string> = {
  failure_classifier: "1 · Failure Classifier",
  customer_profiler: "2 · Customer Profiler",
  strategy_planner: "3 · Strategy Planner",
  policy_guard: "🛡 · Policy Guard",
  graph_branch: "⑂ · LangGraph Branch",
  comms_drafter: "4 · Communication Drafter",
  outcome_evaluator: "5 · Outcome Evaluator",
  defer_to_celery: "⏱ · Defer → Celery",
  finalize_escalate: "⬆ · Escalate Finalize",
  retry_scheduler: "⏱ · Retry Scheduler (Celery)",
  delayed_retry_worker: "⏱ · Delayed Retry Worker",
};

export function AgentTrace({ runId }: Props) {
  const [trace, setTrace] = useState<TraceResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!runId) {
      setTrace(null);
      return;
    }
    let cancelled = false;
    setLoading(true);
    setError(null);
    api
      .trace(runId)
      .then((data) => {
        if (!cancelled) setTrace(data);
      })
      .catch((e: Error) => {
        if (!cancelled) setError(e.message);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [runId]);

  if (!runId) {
    return <p className="empty">Select a recovery row to inspect the full LangGraph agent trace.</p>;
  }
  if (loading) return <p className="loading">Loading agent trace…</p>;
  if (error) return <p className="error">Failed to load trace: {error}</p>;
  if (!trace) return null;

  const draftBody = (trace.drafted_message?.body as string | undefined) ?? null;

  return (
    <div className="trace">
      <div className="toolbar">
        <div>
          <div className="mono">{trace.payment_id}</div>
          <div style={{ color: "var(--muted)", fontSize: "0.85rem" }}>
            {formatInr(trace.amount_paise)} · {trace.failure_type} · {trace.strategy}
          </div>
        </div>
        <span className={`status ${trace.status}`}>{trace.status}</span>
      </div>

      {draftBody ? <div className="draft-box">{draftBody}</div> : null}

      {trace.steps.map((step) => (
        <article key={step.agent} className="trace-step">
          <div className="trace-head">
            <strong>{AGENT_LABEL[step.agent] ?? step.agent}</strong>
            <span className="latency">
              {step.latency_ms != null ? `${step.latency_ms} ms` : ""}
            </span>
          </div>
          {step.reasoning ? <p className="reasoning">{step.reasoning}</p> : null}
          <pre className="pre">{JSON.stringify(step.output, null, 2)}</pre>
        </article>
      ))}
    </div>
  );
}
