import { motion } from "framer-motion";

export function Hero() {
  return (
    <section id="top" className="hero-section">
      <div className="hero-grid" aria-hidden="true" />
      <div className="hero-inner">
        <motion.p
          className="hero-eyebrow"
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5 }}
        >
          Track 3 · Revenue recovery · Built for Razorpay AI Builders
        </motion.p>
        <motion.h1
          className="hero-title"
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.65, delay: 0.08 }}
        >
          Recovery is still done by hand.
          <em> This is the agent loop that fixes it.</em>
        </motion.h1>
        <motion.p
          className="hero-lead"
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.55, delay: 0.18 }}
        >
          ReviveAgent watches failed Razorpay payments, runs a multi-agent LangGraph pipeline,
          drafts the nudge, scores the outcome — and leaves an <strong>Agent Trace</strong> you can
          audit. Scroll. Hover. Click a row. You&apos;ll see the whole system without a walkthrough.
        </motion.p>
        <motion.div
          className="hero-cta"
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5, delay: 0.28 }}
        >
          <a className="btn-primary lg" href="#live">
            Open live console
          </a>
          <a className="btn-ghost" href="#loop">
            How the loop works
          </a>
        </motion.div>
        <motion.ul
          className="hero-tags"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ delay: 0.4, duration: 0.5 }}
        >
          <li>/LANGGRAPH</li>
          <li>/5 AGENTS</li>
          <li>/CELERY DELAY</li>
          <li>/AGENT TRACE</li>
          <li>/PAISE ONLY</li>
        </motion.ul>
      </div>
      <div className="hero-scroll-hint" aria-hidden="true">
        <span>Scroll</span>
        <div className="hero-scroll-line" />
      </div>
    </section>
  );
}
