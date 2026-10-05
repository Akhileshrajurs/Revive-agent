import type { Funnel, RecoveryRun, StrategyPerf } from "../api";
import { AgentTrace } from "./AgentTrace";
import { RecoveryFeed } from "./RecoveryFeed";
import { RecoveryFunnel } from "./RecoveryFunnel";
import { StrategyPerformance } from "./StrategyPerformance";

type Props = {
  rows: RecoveryRun[];
  funnel: Funnel | null;
  perf: StrategyPerf[];
  selectedId: string | null;
  onSelect: (id: string) => void;
  loading: boolean;
  error: string | null;
  onRefresh: () => void;
  liveVisible: boolean;
  justRan?: string | null;
};

export function LiveConsole({
  rows,
  funnel,
  perf,
  selectedId,
  onSelect,
  loading,
  error,
  onRefresh,
  liveVisible,
  justRan,
}: Props) {
  return (
    <section id="live" className="chapter live-section">
      <div className="chapter-inner wide">
        <div className="live-head">
          <div>
            <p className="chapter-kicker">Live console</p>
            <h2 className="chapter-title">
              Real recoveries.
              <em> Click any row for the full Agent Trace.</em>
            </h2>
            <p className="chapter-lead">
              This is the product — not a mock. Feed, funnel, strategy learning, and explainability
              pull from the FastAPI + Postgres stack. Polling only while this section is on screen.
            </p>
          </div>
          <button type="button" className="btn-primary" onClick={onRefresh} disabled={loading}>
            {loading ? "Refreshing…" : "Refresh"}
          </button>
        </div>

        {justRan ? (
          <p className="just-ran banner-ok" role="status">
            Just ran from Play: <strong>{justRan}</strong> — Agent Trace below.
          </p>
        ) : null}

        {error ? (
          <p className="error banner">
            {error} — is the API on :9000?
          </p>
        ) : null}

        {!liveVisible && !rows.length ? (
          <p className="loading">Scroll into view to load live data…</p>
        ) : null}

        <div className="console-grid">
          <article className="panel">
            <h3>Recovery feed</h3>
            <p className="sub">Status colors · amounts in ₹ from paise</p>
            <RecoveryFeed rows={rows} selectedId={selectedId} onSelect={onSelect} />
          </article>

          <article className="panel">
            <h3>Recovery funnel</h3>
            <p className="sub">Failures → attempts → recovered GMV</p>
            <RecoveryFunnel data={funnel} />
          </article>
        </div>

        <div className="console-grid" id="trace">
          <article className="panel panel-trace">
            <h3>Agent Trace</h3>
            <p className="sub">Every LangGraph node · latency · reasoning</p>
            <AgentTrace runId={selectedId} />
          </article>

          <article className="panel">
            <h3>Strategy performance</h3>
            <p className="sub">Agent 5 → Agent 3 learning loop</p>
            <StrategyPerformance rows={perf} />
          </article>
        </div>
      </div>
    </section>
  );
}
