import { motion } from "framer-motion";

const BEATS = [
  { t: "0s", label: "Strategy = delay_and_retry", detail: "Graph takes path_delay. No outcome yet." },
  { t: "T+ε", label: "Status → scheduled", detail: "API enqueues Celery. Request thread stays free." },
  { t: "T+30s", label: "Worker wakes", detail: "Demo countdown (DELAY_RETRY_DEMO_SECONDS). Prod = bank-health delay." },
  { t: "Done", label: "Score + learn", detail: "Outcome evaluator runs; strategy_performance updates." },
] as const;

export function DelayTimeline() {
  return (
    <section id="delay" className="chapter delay-section">
      <div className="chapter-inner">
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true, margin: "-60px" }}
          transition={{ duration: 0.5 }}
        >
          <p className="chapter-kicker">Cool-down path</p>
          <h2 className="chapter-title">
            Bank is down?
            <em> Wait for real. Don&apos;t fake a win.</em>
          </h2>
          <p className="chapter-lead">
            <code>delay_and_retry</code> skips immediate scoring and hands off to Celery + Redis.
            Hover each beat — cool-down belongs on a worker queue, not a request-thread sleep.
          </p>
        </motion.div>

        <ol className="delay-rail">
          {BEATS.map((b, i) => (
            <motion.li
              key={b.t}
              className="delay-beat"
              initial={{ opacity: 0, y: 16 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true }}
              transition={{ delay: i * 0.07, duration: 0.35 }}
            >
              <span className="delay-t mono">{b.t}</span>
              <strong>{b.label}</strong>
              <p>{b.detail}</p>
            </motion.li>
          ))}
        </ol>
      </div>
    </section>
  );
}
