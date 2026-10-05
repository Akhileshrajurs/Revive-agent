import { useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { DEMO_FAILURES, type DemoFailure } from "../demoFailures";

type Props = {
  onSeeItHappen: (demo: DemoFailure) => Promise<void>;
  running: boolean;
};

export function SiteFooter({ onSeeItHappen, running }: Props) {
  const [pick, setPick] = useState<DemoFailure | null>(null);
  const [localError, setLocalError] = useState<string | null>(null);
  const year = new Date().getFullYear();

  const handleSee = async () => {
    if (!pick || running) return;
    setLocalError(null);
    try {
      await onSeeItHappen(pick);
    } catch (e) {
      setLocalError(e instanceof Error ? e.message : "Failed to start recovery");
    }
  };

  return (
    <footer className="site-footer">
      <div className="footer-game">
        <p className="chapter-kicker">Play</p>
        <h2>
          Tap a failure.
          <em> Bet you can predict the branch.</em>
        </h2>
        <div className="fail-keys" role="group" aria-label="Failure simulator">
          {DEMO_FAILURES.map((f) => (
            <button
              key={f.id}
              type="button"
              className={`fail-key ${pick?.id === f.id ? "on" : ""}`}
              disabled={running}
              onClick={() => {
                setPick(f);
                setLocalError(null);
              }}
            >
              {f.label}
            </button>
          ))}
        </div>
        <AnimatePresence mode="wait">
          {pick ? (
            <motion.div
              key={pick.id}
              className="fail-result"
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0 }}
            >
              <span className="mono">{pick.branch}</span>
              <p>
                Likely strategy: <strong>{pick.strategy}</strong>
              </p>
              <button
                type="button"
                className="btn-primary see-happen"
                disabled={running}
                onClick={() => void handleSee()}
              >
                {running ? "Running agents…" : "See it happen in the live console →"}
              </button>
              {localError ? <p className="error footer-run-error">{localError}</p> : null}
            </motion.div>
          ) : (
            <p className="fail-prompt">
              Tap a failure, then run it — real POST → LangGraph → Agent Trace. No fake UI.
            </p>
          )}
        </AnimatePresence>
      </div>

      <div className="footer-bar">
        <div>
          <strong>ReviveAgent</strong>
          <span> · Autonomous payment-failure recovery</span>
        </div>
        <div className="footer-links">
          <a href="#loop">Loop</a>
          <a href="#strategies">Strategies</a>
          <a href="#live">Console</a>
          <a href="#trace">Trace</a>
        </div>
        <p className="footer-copy">
          © {year} · ReviveAgent — payment failure recovery demo (Razorpay Test Mode)
        </p>
      </div>
    </footer>
  );
}
