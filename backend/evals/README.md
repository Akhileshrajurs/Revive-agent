# Recovery evals

Offline + API proofs. No Gemini required.

## Phase 1 — money table

```bash
docker compose run --rm --no-deps api python -m evals.replay --n 2000 --seed 42
```

| System | Policy |
|--------|--------|
| `always_retry` | Every failure → retry |
| `static_map` | Fixed failure→strategy |
| `revive` | Production profiler + planner + **policy** |

Outcomes = Agent 5 simulator. **Not live GMV.**

## Phase 2 — ablation

```bash
docker compose run --rm --no-deps api python -m evals.ablation --n 2000 --seed 42
```

Shows which layer moves recovered ₹ (profile, learning, policy).

## Phase 2 — policy attacks

```bash
docker compose run --rm --no-deps api python -m evals.policy_proof
```

Expect `6/6 passed`.

## Cost + latency

```bash
docker compose run --rm --no-deps api python -m evals.cost_latency --n 200 --seed 42
```

Rules-default → 0 Gemini calls, ₹0 LLM on the decision path.

## Phase 2 — idempotency (API)

```bash
docker compose up -d
python3 scripts/prove_idempotency.py http://localhost:9000
```

Expect 1 unique `run_id`, first fresh + four replays.

## Determinism check

Run Phase 1 twice with `--seed 42`. Recovered ₹ must match.
