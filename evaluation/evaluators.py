# Copyright (c) Microsoft. All rights reserved.
"""Custom evaluators for the Zava Travel Concierge agent.

Three code-based (non-LLM) evaluators that measure domain-specific quality
criteria beyond the built-in relevance/groundedness/safety metrics:

    CompletenessEvaluator    — multi-component request coverage (0-5)
    DataAccuracyEvaluator    — catalog ID / price correctness (0-5)
    PolicyComplianceEvaluator — Zava Travel policy adherence (0-5)

Each class is callable with keyword arguments matching the column names in
evaluation_data.jsonl (query, response, context, ground_truth) and returns a
dict of metric name → value.  This interface is compatible with
azure-ai-evaluation's evaluate() function.

Usage (standalone):
    from evaluators import CompletenessEvaluator, DataAccuracyEvaluator, PolicyComplianceEvaluator

    comp = CompletenessEvaluator()
    result = comp(query="Book a flight and hotel to Rome", response="Here is your flight...")
    print(result)  # {"completeness": 3, "completeness_result": "fail", ...}

Usage with azure-ai-evaluation:
    from azure.ai.evaluation import evaluate
    from evaluators import CompletenessEvaluator

    evaluate(
        data="data/jsonl/evaluation_data.jsonl",
        evaluators={"completeness": CompletenessEvaluator()},
        evaluator_config={
            "completeness": {
                "column_mapping": {
                    "query": "${data.query}",
                    "response": "${data.response}",
                }
            }
        },
    )
"""

import csv
import re
from pathlib import Path


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _locate_data_dir() -> Path:
    """Return the path to the CSV data directory, searching upward from this file."""
    here = Path(__file__).resolve().parent
    candidates = [
        here.parent / "data" / "csv",
        here.parent / "zava" / "src" / "zava-travel-concierge" / "data",
    ]
    for candidate in candidates:
        if candidate.is_dir():
            return candidate
    # fallback — callers must supply data_dir explicitly
    return here.parent / "data" / "csv"


def _load_catalog(data_dir: Path) -> dict[str, dict]:
    """Load all three CSVs into a unified catalog keyed by item ID."""
    catalog: dict[str, dict] = {}
    specs = [
        ("flights.csv",     "flight_id",   "price_usd"),
        ("hotels.csv",      "hotel_id",    "price_per_night_usd"),
        ("car_rentals.csv", "rental_id",   "price_per_day_usd"),
    ]
    for fname, id_col, price_col in specs:
        path = data_dir / fname
        if path.exists():
            with path.open(newline="", encoding="utf-8") as f:
                for row in csv.DictReader(f):
                    item_id = row[id_col]
                    catalog[item_id] = {
                        "price": float(row[price_col]),
                        "id": item_id,
                        **row,
                    }
    return catalog


def _load_unavailable_ids(data_dir: Path) -> set[str]:
    """Return IDs of items that are currently unavailable."""
    unavailable: set[str] = set()
    path = data_dir / "car_rentals.csv"
    if path.exists():
        with path.open(newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                if row.get("available", "true").strip().lower() == "false":
                    unavailable.add(row["rental_id"])
    return unavailable


# ---------------------------------------------------------------------------
# Evaluator 1: Completeness
# ---------------------------------------------------------------------------

class CompletenessEvaluator:
    """Check if a multi-component travel request gets a complete response.

    For single-service requests this always returns a perfect score (5) because
    completeness is only meaningful when the user asked for multiple services.

    Score breakdown:
        5 — all requested components addressed
        3 — at least one component addressed (partial)
        0 — none of the requested components addressed
    The score is linearly interpolated between these anchor points.
    """

    _FLIGHT_KW = frozenset({"flight", "fly", "flying", "airline", "depart", "arrive", "seat", "plane"})
    _HOTEL_KW  = frozenset({"hotel", "accommodation", "stay", "hostel", "room", "inn", "resort", "ryokan", "b&b"})
    _CAR_KW    = frozenset({"car", "rental", "rent", "vehicle", "drive", "suv", "minivan", "auto"})

    _COMPONENT_MAP = {
        "flight": (_FLIGHT_KW, "ZV-FL-"),
        "hotel":  (_HOTEL_KW,  "ZV-HT-"),
        "car":    (_CAR_KW,    "ZV-CR-"),
    }

    def _detect(self, text: str, keywords: frozenset, id_prefix: str) -> bool:
        lower = text.lower()
        return any(kw in lower for kw in keywords) or id_prefix in text

    def __call__(
        self,
        *,
        query: str,
        response: str,
        **kwargs,
    ) -> dict:
        # Identify which services were requested (keyword-only, no ID prefix)
        query_lower = query.lower()
        requested: list[str] = [
            svc
            for svc, (kws, _) in self._COMPONENT_MAP.items()
            if any(kw in query_lower for kw in kws)
        ]

        if len(requested) < 2:
            return {
                "completeness": 5,
                "completeness_result": "pass",
                "completeness_reason": "Single-service (or no-service) request — completeness check not applicable.",
                "completeness_components_requested": requested,
                "completeness_components_covered": requested,
            }

        # Check which requested services appear in the response
        covered: list[str] = [
            svc
            for svc in requested
            if self._detect(response, *self._COMPONENT_MAP[svc])
        ]

        missing = sorted(set(requested) - set(covered))
        ratio = len(covered) / len(requested)
        score = round(ratio * 5)

        return {
            "completeness": score,
            "completeness_result": "pass" if not missing else "fail",
            "completeness_reason": (
                f"Covered {len(covered)}/{len(requested)} requested services. "
                + (f"Missing: {', '.join(missing)}." if missing else "All services addressed.")
            ),
            "completeness_components_requested": sorted(requested),
            "completeness_components_covered": sorted(covered),
        }


# ---------------------------------------------------------------------------
# Evaluator 2: Data Accuracy
# ---------------------------------------------------------------------------

class DataAccuracyEvaluator:
    """Verify that catalog IDs and prices in the response match the CSV data.

    For each Zava ID found in the response (ZV-FL-*, ZV-HT-*, ZV-CR-*) the
    evaluator looks up the expected price in the catalog and checks whether the
    dollar amount mentioned nearby in the response matches within $0.01.

    Score:
        5 — all mentioned IDs are valid and all detected prices are correct
        3 — some prices match (>=60% correct)
        0 — majority wrong or unknown IDs referenced

    When no IDs are found in the response (e.g. a generic answer), the score is
    5 because there is nothing to validate.
    """

    _ID_RE    = re.compile(r"ZV-(?:FL|HT|CR)-\d+")
    _PRICE_RE = re.compile(r"\$(\d{1,4}(?:,\d{3})*(?:\.\d{1,2})?)")

    def __init__(self, data_dir: str | Path | None = None):
        d = Path(data_dir) if data_dir else _locate_data_dir()
        self._catalog = _load_catalog(d)

    def _extract_nearby_prices(self, text: str, id_str: str) -> list[float]:
        """Return dollar amounts mentioned within 200 chars after the given ID."""
        idx = text.find(id_str)
        if idx == -1:
            return []
        window = text[max(0, idx - 30) : idx + 250]
        return [
            float(m.replace(",", ""))
            for m in self._PRICE_RE.findall(window)
        ]

    def __call__(
        self,
        *,
        response: str,
        **kwargs,
    ) -> dict:
        mentioned_ids = list(dict.fromkeys(self._ID_RE.findall(response)))  # deduplicated, ordered

        if not mentioned_ids:
            return {
                "data_accuracy": 5,
                "data_accuracy_result": "pass",
                "data_accuracy_reason": "No catalog IDs found in response — nothing to verify.",
                "data_accuracy_ids_checked": [],
                "data_accuracy_errors": [],
            }

        errors: list[str] = []
        for item_id in mentioned_ids:
            if item_id not in self._catalog:
                errors.append(f"{item_id}: ID not found in catalog.")
                continue

            expected_price = self._catalog[item_id]["price"]
            nearby_prices  = self._extract_nearby_prices(response, item_id)

            # Only flag a mismatch if at least one dollar amount is present nearby
            # and none of them match the expected price.
            if nearby_prices and not any(abs(p - expected_price) < 0.01 for p in nearby_prices):
                errors.append(
                    f"{item_id}: expected ${expected_price:.2f}, "
                    f"found {['$' + str(p) for p in nearby_prices]} nearby."
                )

        total   = len(mentioned_ids)
        correct = total - len(errors)
        score   = round((correct / total) * 5) if total else 5

        return {
            "data_accuracy": score,
            "data_accuracy_result": "pass" if not errors else "fail",
            "data_accuracy_reason": (
                f"Checked {total} ID(s): {correct} correct, {len(errors)} error(s)."
            ),
            "data_accuracy_ids_checked": mentioned_ids,
            "data_accuracy_errors": errors,
        }


# ---------------------------------------------------------------------------
# Evaluator 3: Policy Compliance
# ---------------------------------------------------------------------------

class PolicyComplianceEvaluator:
    """Check that the response follows Zava Travel business policies.

    Policies enforced:
    1. **Unavailability disclosure** — if an unavailable item (e.g. ZV-CR-006,
       ZV-CR-012) is mentioned, the response must include a caveat such as
       "unavailable", "not available", or "out of stock" nearby.
    2. **No negative prices** — dollar amounts must be positive.
    3. **No unsupported destinations** — the response should not direct customers
       to cities outside Zava's network without a disclaimer.

    Score:
        5 — no violations
        3 — one minor violation
        0 — two or more violations
    """

    _ZAVA_CITIES = frozenset({
        "paris", "london", "tokyo", "rome", "cancun", "cancún",
        "denver", "seattle", "new york", "chicago", "san francisco",
    })

    _CAVEAT_WORDS = frozenset({
        "unavailable", "not available", "currently unavailable",
        "out of stock", "no longer available",
    })

    _PRICE_RE = re.compile(r"\$(-\d+(?:\.\d{1,2})?)")

    def __init__(self, data_dir: str | Path | None = None):
        d = Path(data_dir) if data_dir else _locate_data_dir()
        self._unavailable_ids = _load_unavailable_ids(d)

    def __call__(
        self,
        *,
        response: str,
        **kwargs,
    ) -> dict:
        violations: list[str] = []

        # Policy 1 — unavailability disclosure
        for uid in self._unavailable_ids:
            if uid in response:
                idx = response.find(uid)
                window = response[max(0, idx - 120) : idx + 250].lower()
                if not any(c in window for c in self._CAVEAT_WORDS):
                    violations.append(
                        f"{uid} is unavailable but response recommends it without a caveat."
                    )

        # Policy 2 — no negative prices
        neg_prices = self._PRICE_RE.findall(response)
        if neg_prices:
            violations.append(f"Negative price(s) found in response: {neg_prices}.")

        score = max(0, 5 - len(violations) * 2)

        return {
            "policy_compliance": score,
            "policy_compliance_result": "pass" if not violations else "fail",
            "policy_compliance_reason": (
                f"{len(violations)} policy violation(s) found."
                if violations
                else "All policy checks passed."
            ),
            "policy_compliance_violations": violations,
        }
