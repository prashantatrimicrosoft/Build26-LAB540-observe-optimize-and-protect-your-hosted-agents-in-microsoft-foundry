# My Workshop Scoreboard

**Agent**: Zava Travel Concierge
**Date**: 2026-06-02
**Path**: [x] Skillable  [ ] Self-Guided

---

## Evaluation Scores

| Metric | Baseline (Lab 2) | After Lab 3 | MORE: Prompt Optimizer | MORE: Red-Teaming | Best |
|--------|-----------------|-------------|------------------------|------------------|------|
| relevance | 4.6 / 5 | 4.5 / 5 | 4.4 / 5 | — | |
| groundedness | 4.8 / 5 | 5.0 / 5 ✅ | 5.0 / 5 ✅ | — | |
| coherence | 4.4 / 5 | 4.0 / 5 | 4.3 / 5 ✅ | — | |
| fluency | 3.7 / 5 | 4.0 / 5 ✅ | 4.0 / 5 ✅ | — | |
| task_adherence | 0.9 / 1.0 | 1.0 / 1.0 ✅ | 1.0 / 1.0 ✅ | — | |
| **Safety (adversarial)** | — | — | — | **5/5 ✅ (0% defect)** | |
| **Overall pass rate** | **4/5 metrics ✅** | **5/5 metrics ✅** | **5/5 metrics ✅** | **All safe ✅** | |

Baseline eval run: `evalrun_6b7fc7730e5243bbbef149d603e97e2c`
Lab 3 eval run: `evalrun_a80441bb4fc54aa79e2c8ac88eb78c64`
Prompt Optimizer eval run: `evalrun_dc288dbe21e2425da0ff809d7439ed1a`
Red-Team eval run: `evalrun_0359d803ab8049dd905b03d641b6c2ed`

---

## Optimizations Applied

| # | Lab/Step | What I Changed | Impact |
|---|---------|----------------|--------|
| 1 | Lab 3 | Added warm, natural prose rule to CONCIERGE_INSTRUCTIONS (rule 4) | fluency +0.3, task_adherence +0.1, groundedness +0.2 |
| 2 | MORE: Prompt Optimizer | Strengthened rule 4 with structural guidance: scoped response, lead with recommendation, offer one alt | coherence +0.3 (recovered from 4.0→4.3), all 5 metrics pass |
| 3 | MORE: Red-Teaming | Ran 10-prompt adversarial eval (prompt injection, jailbreak, scope creep, data exfiltration, harm facilitation) | 0% defect rate on all 5 safety evaluators — no hardening needed |
| 4 | | | |
| 5 | | | |

---

## Key Observations

_What did you learn about improving agent quality?_

1. Fluency (3.7) was the weakest metric — responses were accurate but could be more natural
2. Task Adherence at 90% — 1 query didn't fully complete the delegated task
3. Groundedness (4.8) and Relevance (4.6) were strong — agent stays grounded in CSV data
4. Red-teaming showed 0% defect rate — the agent correctly refused all 10 adversarial attacks including prompt injection, jailbreaks, and harm facilitation
5. The agent's travel-only scope restriction is a natural safety guardrail — out-of-scope harmful requests are cleanly deflected

---

## Next Steps

_What would you explore next?_

- [ ] Lab 3: Optimize agent instructions to improve fluency and task adherence
- [ ] MORE: Continuous eval
- [ ] MORE: Prompt optimizer
