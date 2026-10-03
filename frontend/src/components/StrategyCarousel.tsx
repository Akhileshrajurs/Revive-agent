import { useState } from "react";
import { AnimatePresence, motion } from "framer-motion";

const STRATEGIES = [
  {
    id: "retry_same_method",
    title: "Retry same method",
    when: "Transient blips, soft declines, customer still online.",
    path: "path_retry",
    tip: "Same rail, fresh attempt — no method switch friction.",
  },
  {
    id: "suggest_alternate_method",
    title: "Suggest alternate method",
    when: "Instrument failure, unsupported method, or card/UPI mismatch.",
    path: "path_alternate",
    tip: "Nudge to UPI / another card before they bounce.",
  },
  {
    id: "offer_emi",
    title: "Offer EMI",
    when: "High ticket + affordability signal.",
    path: "path_emi",
    tip: "Split the ticket — keep the conversion, lower the shock.",
  },
  {
    id: "offer_partial_payment",
    title: "Offer partial payment",
    when: "Balance / limit issues on large carts.",
    path: "path_partial",
    tip: "Recover something now; finish the rest later.",
  },
  {
    id: "delay_and_retry",
    title: "Delay & retry",
    when: "Bank technical errors, netbanking outages.",
    path: "path_delay → Celery",
    tip: "No fake instant win. Schedule cool-down; worker scores later.",
  },
  {
    id: "escalate_to_human",
    title: "Escalate to human",
    when: "Fraud risk, max retries, or unknown taxonomy.",
    path: "path_escalate",
    tip: "Fail closed on payment actions. Humans own the edge cases.",
  },
] as const;

export function StrategyCarousel() {
  const [i, setI] = useState(0);
  const card = STRATEGIES[i];

  const prev = () => setI((v) => (v - 1 + STRATEGIES.length) % STRATEGIES.length);
  const next = () => setI((v) => (v + 1) % STRATEGIES.length);

  return (
    <section id="strategies" className="chapter strategies-section">
      <div className="chapter-inner">
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true, margin: "-60px" }}
          transition={{ duration: 0.5 }}
        >
          <p className="chapter-kicker">Six branches</p>
          <h2 className="chapter-title">
            Same failure. Different play.
            <em> Swipe the strategy deck.</em>
          </h2>
          <p className="chapter-lead">
            LangGraph routes each run to a real path node. Hover the dots — or use prev/next —
            to see when each strategy fires.
          </p>
        </motion.div>

        <div className="carousel">
          <button type="button" className="carousel-nav" aria-label="Previous card" onClick={prev}>
            ←
          </button>

          <div className="carousel-stage">
            <AnimatePresence mode="wait">
              <motion.article
                key={card.id}
                className="strategy-card"
                initial={{ opacity: 0, x: 28 }}
                animate={{ opacity: 1, x: 0 }}
                exit={{ opacity: 0, x: -28 }}
                transition={{ duration: 0.28 }}
              >
                <span className="strategy-path mono">{card.path}</span>
                <h3>{card.title}</h3>
                <p className="strategy-when">
                  <strong>When:</strong> {card.when}
                </p>
                <p className="strategy-tip">{card.tip}</p>
                <span className="strategy-count">
                  {i + 1} / {STRATEGIES.length}
                </span>
              </motion.article>
            </AnimatePresence>
          </div>

          <button type="button" className="carousel-nav" aria-label="Next card" onClick={next}>
            →
          </button>
        </div>

        <div className="carousel-dots" role="tablist" aria-label="Strategy cards">
          {STRATEGIES.map((s, idx) => (
            <button
              key={s.id}
              type="button"
              role="tab"
              aria-selected={idx === i}
              aria-label={`Go to card ${idx + 1}: ${s.title}`}
              className={idx === i ? "on" : ""}
              onClick={() => setI(idx)}
              title={s.title}
            />
          ))}
        </div>
      </div>
    </section>
  );
}
