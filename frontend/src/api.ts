const API_BASE = import.meta.env.VITE_API_BASE ?? "http://localhost:9000";

/** Recovery POST must stay snappy — never leave "Running agents…" spinning. */
const POST_TIMEOUT_MS = 12_000;
const GET_TIMEOUT_MS = 8_000;

export type RecoveryRun = {
  id: string;
  payment_id: string;
  amount_paise: number;
  currency: string;
  payment_method: string | null;
  failure_type: string | null;
  failure_confidence: number | null;
  strategy: string | null;
  status: string;
  agent_trace: { steps?: TraceStep[] };
  customer_profile: Record<string, unknown> | null;
  strategy_decision: Record<string, unknown> | null;
  drafted_message: Record<string, unknown> | null;
  outcome: Record<string, unknown> | null;
  created_at: string;
};

export type TraceStep = {
  agent: string;
  status: string;
  output: Record<string, unknown>;
  reasoning?: string | null;
  latency_ms?: number | null;
};

export type Funnel = {
  failures: number;
  attempted: number;
  recovered: number;
  escalated: number;
  revenue_saved_paise: number;
  by_failure_type: Record<string, number>;
};

export type StrategyPerf = {
  strategy: string;
  failure_type: string;
  attempts: number;
  successes: number;
  recovery_rate: number;
};

export type TraceResponse = {
  run_id: string;
  payment_id: string;
  amount_paise: number;
  status: string;
  failure_type: string | null;
  strategy: string | null;
  customer_profile: Record<string, unknown> | null;
  strategy_decision: Record<string, unknown> | null;
  drafted_message: Record<string, unknown> | null;
  outcome: Record<string, unknown> | null;
  steps: TraceStep[];
};

export type CreateRecoveryBody = {
  payment_id: string;
  order_id?: string;
  customer_id?: string;
  amount_paise: number;
  currency?: string;
  method?: string;
  error_code?: string;
  error_description?: string;
  error_reason?: string;
  customer_name?: string;
  merchant_name?: string;
};

export type CreateRecoveryResponse = {
  run_id: string;
  payment_id: string;
  status: string;
  classification: { failure_type: string; confidence: number; reasoning: string };
  strategy_decision: { strategy: string; reasoning: string } | null;
  agent_trace: TraceStep[];
};

async function fetchWithTimeout(
  url: string,
  init: RequestInit | undefined,
  timeoutMs: number,
): Promise<Response> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    return await fetch(url, { ...init, signal: controller.signal });
  } catch (err) {
    if (err instanceof DOMException && err.name === "AbortError") {
      throw new Error(`timeout after ${timeoutMs}ms — ${url.replace(API_BASE, "")}`);
    }
    throw err;
  } finally {
    clearTimeout(timer);
  }
}

async function getJson<T>(path: string): Promise<T> {
  const res = await fetchWithTimeout(`${API_BASE}${path}`, undefined, GET_TIMEOUT_MS);
  if (!res.ok) throw new Error(`${res.status} ${path}`);
  return res.json() as Promise<T>;
}

async function postJson<T>(path: string, body: unknown): Promise<T> {
  const res = await fetchWithTimeout(
    `${API_BASE}${path}`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    },
    POST_TIMEOUT_MS,
  );
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`${res.status} ${path}${text ? `: ${text.slice(0, 180)}` : ""}`);
  }
  return res.json() as Promise<T>;
}

export const api = {
  recoveries: (limit = 50) => getJson<RecoveryRun[]>(`/api/v1/recoveries?limit=${limit}`),
  funnel: () => getJson<Funnel>("/api/v1/analytics/funnel"),
  strategyPerformance: () =>
    getJson<StrategyPerf[]>("/api/v1/analytics/strategy-performance"),
  trace: (runId: string) => getJson<TraceResponse>(`/api/v1/recoveries/${runId}/trace`),
  createRecovery: (body: CreateRecoveryBody) =>
    postJson<CreateRecoveryResponse>("/api/v1/recoveries", body),
};

export function formatInr(paise: number): string {
  return new Intl.NumberFormat("en-IN", {
    style: "currency",
    currency: "INR",
    maximumFractionDigits: 0,
  }).format(paise / 100);
}
