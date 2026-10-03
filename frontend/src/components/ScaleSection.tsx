import { motion } from "framer-motion";

const TIERS = [
  {
    tier: "Demo-now",
    items: ["This page + live API", "LangGraph branches", "Celery demo countdown", "Agent Trace exportable"],
  },
  {
    tier: "Merchant-scale",
    items: ["Webhooks → SQS/Kafka", "Idempotent workers", "WhatsApp templates + DNC", "Postgres truth + Redis locks"],
  },
  {
    tier: "Razorpay-scale",
    items: ["UPI peak partitions", "Backpressure + SLOs", "Multi-region hot path", "Outcome warehouse learning"],
  },
] as const;

export function ScaleSection() {
  return (
    <section id="scale" className="chapter scale-section">
      <div className="chapter-inner">
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true, margin: "-60px" }}
          transition={{ duration: 0.5 }}
        >
          <p className="chapter-kicker">Architecture path</p>
          <h2 className="chapter-title">
            Honest about volume.
            <em> Ambitious about the path.</em>
          </h2>
          <p className="chapter-lead">
            Local Docker is not billions of txns. Hover a tier — this is how an AI Builder would grow
            Track 3 recovery from demo → merchant → India-scale traffic.
          </p>
        </motion.div>

        <div className="scale-grid">
          {TIERS.map((t, i) => (
            <motion.article
              key={t.tier}
              className="scale-card"
              initial={{ opacity: 0, y: 18 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true }}
              transition={{ delay: i * 0.08, duration: 0.4 }}
            >
              <h3>{t.tier}</h3>
              <ul>
                {t.items.map((item) => (
                  <li key={item}>{item}</li>
                ))}
              </ul>
            </motion.article>
          ))}
        </div>
      </div>
    </section>
  );
}
