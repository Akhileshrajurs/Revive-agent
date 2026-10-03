import { motion } from "framer-motion";

const STEPS = [
  {
    n: "1/",
    title: "Payment fails",
    body: "Razorpay error codes land. No sync LLM on the hot path — classify with rules first.",
  },
  {
    n: "2/",
    title: "Agents decide",
    body: "Classify → profile → plan → branch → draft. Six strategy paths. Structured outputs only.",
  },
  {
    n: "3/",
    title: "Act & learn",
    body: "Message the customer, or Celery-schedule a cool-down. Outcome feeds strategy performance.",
  },
] as const;

export function WhatSection() {
  return (
    <section id="what" className="chapter what-section">
      <div className="chapter-inner">
        <motion.div
          className="what-copy"
          initial={{ opacity: 0, y: 24 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true, margin: "-80px" }}
          transition={{ duration: 0.55 }}
        >
          <p className="chapter-kicker">What this is</p>
          <h2 className="chapter-title">
            Not a chatbot wrapper.
            <em> A recovery state machine for Indian checkout.</em>
          </h2>
          <p className="chapter-lead">
            Merchants still chase failed UPI, cards, and netbanking by hand. ReviveAgent turns that
            into Perceive → Plan → Act → Evaluate — with every decision explainable in the Agent Trace.
            The system you&apos;d put next to Checkout volume, not a weekend script.
          </p>
        </motion.div>

        <div className="process-list">
          {STEPS.map((s, i) => (
            <motion.article
              key={s.n}
              className="process-row"
              initial={{ opacity: 0, x: -16 }}
              whileInView={{ opacity: 1, x: 0 }}
              viewport={{ once: true, margin: "-40px" }}
              transition={{ duration: 0.4, delay: i * 0.08 }}
            >
              <span className="process-n">{s.n}</span>
              <div>
                <h3>{s.title}</h3>
                <p>{s.body}</p>
              </div>
            </motion.article>
          ))}
        </div>
      </div>
    </section>
  );
}
