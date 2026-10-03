import { useState } from "react";
import { AnimatePresence, motion } from "framer-motion";

type NodeInfo = {
  id: string;
  label: string;
  short: string;
  input: string;
  output: string;
  detail: string;
};

const NODES: NodeInfo[] = [
  {
    id: "failure_classifier",
    label: "1 · Classifier",
    short: "Classify",
    input: "error_code, error_reason, method",
    output: "failure_type + confidence",
    detail:
      "Rules map Razorpay errors (insufficient_funds, bank_technical_error, …) to a typed taxonomy. No LLM guesswork on money-critical labels.",
  },
  {
    id: "customer_profiler",
    label: "2 · Profiler",
    short: "Profile",
    input: "payment history, method prefs",
    output: "risk + retry windows",
    detail:
      "Builds a customer payment profile — preferred methods, prior failures, quiet hours — so strategy isn’t one-size-fits-all.",
  },
  {
    id: "strategy_planner",
    label: "3 · Planner",
    short: "Plan",
    input: "failure + profile + learning rates",
    output: "RecoveryStrategy (enum)",
    detail:
      "Picks a structured strategy. Gemini only drafts reasoning text — the choice itself is rules + performance stats.",
  },
  {
    id: "graph_branch",
    label: "⑂ · Branch",
    short: "Branch",
    input: "strategy enum",
    output: "one of 6 path_* nodes",
    detail:
      "Real LangGraph conditional edges — not a straight line. retry · alternate · EMI · partial · delay → Celery · escalate.",
  },
  {
    id: "comms_drafter",
    label: "4 · Comms",
    short: "Draft",
    input: "strategy + customer name",
    output: "message body + CTA",
    detail:
      "Templates + Gemini copy for WhatsApp/SMS-ready nudges. Idempotent intent: same payment_id shouldn’t double-message.",
  },
  {
    id: "outcome_path",
    label: "5 · Outcome / Defer",
    short: "Score",
    input: "drafted action + strategy",
    output: "outcome or scheduled",
    detail:
      "Immediate score — or skip to Celery when delay_and_retry. Zero sleep on the request path. Learning writes strategy_performance.",
  },
];

type Props = {
  activeAgent?: string | null;
  onPick?: (id: string) => void;
};

export function AgentLoop({ activeAgent, onPick }: Props) {
  const [hover, setHover] = useState<string | null>(null);
  const selected = hover ?? activeAgent ?? NODES[0].id;
  const info = NODES.find((n) => n.id === selected) ?? NODES[0];

  return (
    <section id="loop" className="chapter loop-section">
      <div className="chapter-inner">
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true, margin: "-60px" }}
          transition={{ duration: 0.5 }}
        >
          <p className="chapter-kicker">The loop</p>
          <h2 className="chapter-title">
            Hover any node.
            <em> That&apos;s the agent contract.</em>
          </h2>
          <p className="chapter-lead">
            Clear input → structured output → typed errors. When you click a recovery in Live Console,
            the matching steps light up in Agent Trace below.
          </p>
        </motion.div>

        <div className="loop-layout">
          <div className="loop-rail" role="list">
            {NODES.map((n, i) => {
              const isOn = selected === n.id || activeAgent === n.id;
              return (
                <button
                  key={n.id}
                  type="button"
                  role="listitem"
                  className={`loop-node ${isOn ? "on" : ""}`}
                  onMouseEnter={() => setHover(n.id)}
                  onMouseLeave={() => setHover(null)}
                  onFocus={() => setHover(n.id)}
                  onClick={() => {
                    setHover(n.id);
                    onPick?.(n.id);
                    document.getElementById("trace")?.scrollIntoView({ behavior: "smooth" });
                  }}
                >
                  <span className="loop-idx">{String(i + 1).padStart(2, "0")}</span>
                  <span className="loop-label">{n.short}</span>
                  {i < NODES.length - 1 ? <span className="loop-connector" aria-hidden="true" /> : null}
                </button>
              );
            })}
          </div>

          <AnimatePresence mode="wait">
            <motion.aside
              key={info.id}
              className="loop-detail"
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -6 }}
              transition={{ duration: 0.22 }}
            >
              <h3>{info.label}</h3>
              <p>{info.detail}</p>
              <dl className="loop-io">
                <div>
                  <dt>In</dt>
                  <dd>{info.input}</dd>
                </div>
                <div>
                  <dt>Out</dt>
                  <dd>{info.output}</dd>
                </div>
              </dl>
              <p className="loop-hint">Click → jump to Agent Trace</p>
            </motion.aside>
          </AnimatePresence>
        </div>
      </div>
    </section>
  );
}
