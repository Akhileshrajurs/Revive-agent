import { useCallback, useEffect, useRef, useState } from "react";
import {
  api,
  type Funnel,
  type RecoveryRun,
  type StrategyPerf,
} from "./api";
import { AgentLoop } from "./components/AgentLoop";
import { DelayTimeline } from "./components/DelayTimeline";
import { Hero } from "./components/Hero";
import { LiveConsole } from "./components/LiveConsole";
import { ScaleSection } from "./components/ScaleSection";
import { SiteFooter } from "./components/SiteFooter";
import { SiteNav } from "./components/SiteNav";
import { StrategyCarousel } from "./components/StrategyCarousel";
import { WhatSection } from "./components/WhatSection";
import { buildDemoPayment, type DemoFailure } from "./demoFailures";

export default function App() {
  const [rows, setRows] = useState<RecoveryRun[]>([]);
  const [funnel, setFunnel] = useState<Funnel | null>(null);
  const [perf, setPerf] = useState<StrategyPerf[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [liveVisible, setLiveVisible] = useState(false);
  const [activeAgent, setActiveAgent] = useState<string | null>(null);
  const [demoRunning, setDemoRunning] = useState(false);
  const [justRan, setJustRan] = useState<string | null>(null);
  const liveRef = useRef<HTMLDivElement>(null);

  const refresh = useCallback(async (preferId?: string) => {
    setLoading(true);
    setError(null);
    try {
      const [r, f, p] = await Promise.all([
        api.recoveries(40),
        api.funnel(),
        api.strategyPerformance(),
      ]);
      setRows(r);
      setFunnel(f);
      setPerf(p);
      setSelectedId((prev) => preferId ?? prev ?? r[0]?.id ?? null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load dashboard");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    const el = liveRef.current;
    if (!el) return;
    const io = new IntersectionObserver(
      ([entry]) => {
        if (entry?.isIntersecting) setLiveVisible(true);
      },
      { rootMargin: "120px", threshold: 0.05 },
    );
    io.observe(el);
    return () => io.disconnect();
  }, []);

  useEffect(() => {
    if (!liveVisible) return;
    void refresh();
    const id = window.setInterval(() => void refresh(), 15000);
    return () => window.clearInterval(id);
  }, [liveVisible, refresh]);

  useEffect(() => {
    const steps = rows.find((r) => r.id === selectedId)?.agent_trace?.steps;
    const last = steps?.[steps.length - 1]?.agent ?? null;
    setActiveAgent(last);
  }, [rows, selectedId]);

  const onSelect = (id: string) => {
    setSelectedId(id);
    setJustRan(null);
    document.getElementById("trace")?.scrollIntoView({ behavior: "smooth", block: "nearest" });
  };

  const onSeeItHappen = useCallback(
    async (demo: DemoFailure) => {
      setDemoRunning(true);
      setError(null);
      setLiveVisible(true);
      try {
        const body = buildDemoPayment(demo);
        const created = await api.createRecovery(body);
        const runId = String(created.run_id);
        await refresh(runId);
        setSelectedId(runId);
        setJustRan(
          `${demo.label} → ${created.strategy_decision?.strategy ?? "—"} · ${created.status}`,
        );
        requestAnimationFrame(() => {
          document.getElementById("trace")?.scrollIntoView({ behavior: "smooth", block: "start" });
        });
      } catch (err) {
        const msg = err instanceof Error ? err.message : "Recovery request failed";
        setError(msg);
        setJustRan(null);
      } finally {
        setDemoRunning(false);
      }
    },
    [refresh],
  );

  return (
    <div className="app-shell">
      <SiteNav />
      <Hero />
      <WhatSection />
      <AgentLoop activeAgent={activeAgent} onPick={setActiveAgent} />
      <StrategyCarousel />
      <DelayTimeline />
      <div ref={liveRef}>
        <LiveConsole
          rows={rows}
          funnel={funnel}
          perf={perf}
          selectedId={selectedId}
          onSelect={onSelect}
          loading={loading || demoRunning}
          error={error}
          onRefresh={() => void refresh()}
          liveVisible={liveVisible}
          justRan={justRan}
        />
      </div>
      <ScaleSection />
      <SiteFooter onSeeItHappen={onSeeItHappen} running={demoRunning} />
    </div>
  );
}
