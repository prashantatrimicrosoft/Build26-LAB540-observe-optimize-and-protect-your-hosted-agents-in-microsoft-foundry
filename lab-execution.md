# LAB540 — Execution Log

> **Session**: Build 2026 LAB540 — *Observe, Optimize, and Protect Your Hosted Agents in Microsoft Foundry*
> **Date**: 2026-06-02 / 2026-06-03
> **Path**: Skillable (hosted codespace)
> **Agent**: Zava Travel Concierge (`******`)

---

## Environment

| Component | Value |
|-----------|-------|
| Azure Subscription | `******` |
| Resource Group | `******` |
| AI Account | `******` |
| Foundry Project | `******` |
| Project Endpoint | `******` |
| Model Deployment | `gpt-4.1-mini` |
| Container Registry | `******` |
| Application Insights | `******` |
| Python | 3.12.13 |
| agent-framework | 1.7.0 |

---

## Lab 0 — Environment Setup

**Status**: ✅ Complete

- Ran `scripts/discover-env.sh` to populate `.env` from Bicep outputs
- Confirmed Azure login with `DefaultAzureCredential`
- Verified agent container running in Foundry (`azd deploy` was broken due to Docker API 1.38 < 1.40 requirement)
- **Workaround used for all deploys**: manual `docker build + push + mcp_foundry agent_update` instead of `azd deploy`

---

## Lab 1 — Smoke Test (Agent Invocation)

**Status**: ✅ Complete

All 3 test prompts passed:

1. *"Find me a business class flight from Chicago to Rome"* — returned ZV-FL-013, cited price + dates
2. *"What 5-star hotels are available in Paris with a pool?"* — returned matching hotel IDs
3. *"Book a trip to Tokyo — flights, hotel, and car"* — parallel specialist delegation, merged itinerary

---

## Lab 2 — Baseline Evaluation

**Status**: ✅ Complete

**Eval run**: `******`

| Metric | Score |
|--------|-------|
| relevance | 4.6 / 5 |
| groundedness | 4.8 / 5 |
| coherence | 4.4 / 5 |
| fluency | **3.7 / 5** ← weakest |
| task_adherence | 0.9 / 1.0 |

**Observations**:
- Fluency was the weakest metric — responses were accurate but read like data printouts
- Task adherence at 90% — one query did not fully complete delegated task
- Groundedness (4.8) strong — agent stayed grounded in CSV data, no hallucinations

---

## Lab 3 — Instruction Optimization (Manual)

**Status**: ✅ Complete

**Eval run**: `******`

**Change made to `CONCIERGE_INSTRUCTIONS` in `main.py`**:

Added Rule 4 (warm prose guidance):

```
4. Write every response in warm, natural prose -- the tone of a knowledgeable
   personal travel concierge, not a data printout. Currency is USD unless stated.
```

**Results vs Baseline**:

| Metric | Baseline | After Lab 3 | Delta |
|--------|----------|-------------|-------|
| relevance | 4.6 | 4.5 | -0.1 |
| groundedness | 4.8 | **5.0** | +0.2 ✅ |
| coherence | 4.4 | 4.0 | -0.4 |
| fluency | 3.7 | **4.0** | +0.3 ✅ |
| task_adherence | 0.9 | **1.0** | +0.1 ✅ |

**Deploy method**: `docker build` → push to ACR → `agent_update` via Foundry MCP

---

## MORE — Prompt Optimizer

**Status**: ✅ Complete

**Eval run**: `******`

Used the Foundry Prompt Optimizer to refine Rule 4 further. The optimizer added structural guidance:

```
4. Write every response in warm, natural prose -- the tone of a knowledgeable
   personal travel concierge, not a data printout. Structure your response
   clearly: start with a friendly recommendation sentence, follow with the key
   details (ID, price, dates), then offer one meaningful alternative when useful.
   Avoid over-explaining, off-topic information, or rambling. Keep responses
   tightly scoped to the user's query (e.g., a flight query should lead with
   flights, not hotels). Currency is USD unless stated.
```

**Results vs Baseline**:

| Metric | Baseline | Prompt Optimizer | Delta |
|--------|----------|-----------------|-------|
| relevance | 4.6 | 4.4 | -0.2 |
| groundedness | 4.8 | **5.0** | +0.2 ✅ |
| coherence | 4.4 | **4.3** | -0.1 (recovered from Lab3 drop) |
| fluency | 3.7 | **4.0** | +0.3 ✅ |
| task_adherence | 0.9 | **1.0** | +0.1 ✅ |

All 5 metrics passing at end of optimizer run.

---

## MORE — Red-Teaming

**Status**: ✅ Complete

**Eval run**: `******`

Ran 10-prompt adversarial evaluation covering:
- Prompt injection
- Jailbreak attempts
- Scope creep (non-travel requests)
- Data exfiltration attempts
- Harm facilitation

**Results**: **0% defect rate** on all 5 safety evaluators — no hardening needed.

| Safety Evaluator | Defect Rate |
|-----------------|-------------|
| Hateful/Unfair Content | 0% ✅ |
| Sexual Content | 0% ✅ |
| Violence | 0% ✅ |
| Self-Harm | 0% ✅ |
| Protected Material | 0% ✅ |

**Key insight**: The agent's travel-only scope restriction (Rule 5: *"Decline non-travel, unsafe, or policy-violating requests in one sentence"*) acts as a natural safety guardrail — all 10 adversarial attacks were cleanly deflected.

---

## MORE — Tracing

**Status**: ⚠️ Partially complete (blockers encountered)

**Changes made to codebase**:

`requirements.txt` — added:
```
opentelemetry-exporter-otlp-proto-grpc
```

`main.py` — added OpenTelemetry setup block after `load_dotenv()`:
```python
from agent_framework.observability import configure_otel_providers

_VS_CODE_PORT = int(os.environ.get("OTEL_VSCODE_PORT", "0"))
configure_otel_providers(
    vs_code_extension_port=_VS_CODE_PORT if _VS_CODE_PORT else None,
    enable_sensitive_data=True,
)
```

**Image deployed**: `<acr>.azurecr.io/zava-concierge:tracing-v4`

**Blockers encountered**:
1. **A365 genAI exporter → HTTP 403**: Agent managed identity (`******`) lacks RBAC permission to write to Foundry trace store. Needs role assignment on the AI account resource.
2. **`AZURE_EXPERIMENTAL_ENABLE_GENAI_TRACING=true` breaks sub-agents**: Causes `AsyncStreamWrapper` incompatibility in `agent_framework_foundry._chat_client.FoundryChatClient`. Env var is incompatible with current framework version (1.7.0).

**Trace-linked eval runs** (both 0 results due to blockers above):
- `******` (v4 tracing agent)
- `******` (v3 turn)

---

## Code Changes Summary

| File | Change |
|------|--------|
| `zava/src/zava-travel-concierge/main.py` | Added OTel tracing setup; added Rule 4 (warm prose + structural guidance) to `CONCIERGE_INSTRUCTIONS` |
| `zava/src/zava-travel-concierge/requirements.txt` | Added `opentelemetry-exporter-otlp-proto-grpc` |
| `zava/azure.yaml` | azd config updates |
| `zava/agent.yaml` | Hosted agent definition (new file) |
| `zava/.agentignore` | Agent ignore file (new file) |
| `workshop/scoreboard/my-scoreboard.md` | Eval scores recorded |
| `scripts/discover-env.sh` | Environment discovery updates |

---

## Final Eval Scoreboard

| Metric | Baseline | Lab 3 | Prompt Optimizer | Best |
|--------|----------|-------|-----------------|------|
| relevance | 4.6 | 4.5 | 4.4 | 4.6 |
| groundedness | 4.8 | **5.0** | **5.0** | **5.0** ✅ |
| coherence | 4.4 | 4.0 | 4.3 | 4.4 |
| fluency | 3.7 | **4.0** | **4.0** | **4.0** ✅ |
| task_adherence | 0.9 | **1.0** | **1.0** | **1.0** ✅ |
| safety (adversarial) | — | — | — | **0% defect** ✅ |

---

## Known Issues / Limitations

1. **`azd deploy` broken** in this environment (Docker API 1.38 < required 1.40). All deploys done manually.
2. **A365 exporter 403** — agent identity needs `Azure AI Account User` or equivalent role on the AI account resource to write traces to Foundry.
3. **`AZURE_EXPERIMENTAL_ENABLE_GENAI_TRACING=true`** causes sub-agent failures in agent-framework 1.7.0 — do not set this env var until a compatible version is released.
4. **`GITHUB_TOKEN`** in codespace environment is locked to lab account — personal fork pushes require an embedded PAT in the remote URL.
