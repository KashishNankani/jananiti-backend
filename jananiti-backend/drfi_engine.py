"""
drfi_engine.py
Development Resource & Fairness Index (DRFI) — the core deterministic scoring
engine. Pure Python, no ML library required. Complements the LLM-generated
rankings with an explainable, formula-based score per block+category.
"""

URGENCY_WEIGHTS = {"critical": 4, "high": 3, "medium": 2, "low": 1}

COMPONENT_WEIGHTS = {
    "citizen_demand": 0.25,
    "demographic_need": 0.20,
    "infrastructure_gap": 0.15,
    "equity": 0.15,
    "plan_alignment": 0.10,
    "cost_effectiveness": 0.10,
    "cascading_impact": 0.05,
}


def _clamp(x, lo=0, hi=100):
    return max(lo, min(hi, x))


def _citizen_demand_score(submissions_for_block: list) -> float:
    n = len(submissions_for_block)
    if n == 0:
        return 0.0
    base = min(n * 5, 100)

    urgency_vals = [
        URGENCY_WEIGHTS.get((s.get("urgency_level") or "low"), 1) for s in submissions_for_block
    ]
    mean_urgency = sum(urgency_vals) / len(urgency_vals)
    urgency_boost = (mean_urgency / 4) * 20

    negative_sentiment_count = sum(
        1 for s in submissions_for_block if s.get("sentiment") in ("desperate", "frustrated")
    )
    sentiment_boost = (negative_sentiment_count / n) * 15

    return _clamp(base + urgency_boost + sentiment_boost)


def _demographic_need_score(block: dict, category: str) -> float:
    population = max(block.get("population") or 1, 1)
    bpl_households = block.get("bpl_households") or 0
    children = block.get("children_6_14") or 0

    if category == "Education":
        school_capacity_used = block.get("school_capacity_used") or 0
        score = (children / population) * 100 * (school_capacity_used / 100)
    elif category == "Healthcare":
        score = ((block.get("nearest_hospital_km") or 0) / 30) * 100
    elif category == "Roads":
        score = 100 - (block.get("road_paved_percent") or 0)
    elif category in ("Water", "Sanitation"):
        score = (bpl_households / population) * 100
    else:
        score = (bpl_households / population) * 80

    return _clamp(score)


def _infrastructure_gap_score(block: dict, category: str) -> float:
    if category == "Education":
        km = block.get("nearest_school_km") or 0
        score = max(0, km - 1.0) / 15 * 100
    elif category == "Healthcare":
        km = block.get("nearest_hospital_km") or 0
        score = max(0, km - 3.0) / 30 * 100
    elif category == "Roads":
        score = 100 - (block.get("road_paved_percent") or 0)
    else:
        score = 50

    return _clamp(score)


def _equity_score(block: dict) -> float:
    population = max(block.get("population") or 1, 1)
    sc_st_score = block.get("sc_st_percent") or 0
    bpl_score = min(((block.get("bpl_households") or 0) / population) * 100 * 2, 100)
    return _clamp((sc_st_score + bpl_score) / 2)


def _plan_alignment_score(block: dict) -> float:
    plans = (block.get("existing_plans") or "").lower()
    if "completed" in plans:
        return 10
    if "underway" in plans or "active" in plans:
        return 30
    if "proposed" in plans or "sanctioned" in plans:
        return 50
    if "stalled" in plans:
        return 70
    if not plans.strip():
        return 90
    return 60


def _cost_effectiveness_score(block: dict, category: str) -> float:
    population = block.get("population") or 1
    if category == "Education":
        beneficiaries = block.get("children_6_14") or 1
    elif category == "Healthcare":
        beneficiaries = population
    else:
        beneficiaries = population

    beneficiaries = max(beneficiaries, 1)
    score = min(100 / max(beneficiaries / 1000, 1), 100)
    return _clamp(score)


def _cascading_impact_score(block: dict, category: str) -> float:
    sc_st_percent = block.get("sc_st_percent") or 0
    nearest_school_km = block.get("nearest_school_km") or 0
    nearest_hospital_km = block.get("nearest_hospital_km") or 0

    severely_underserved = sc_st_percent > 60 and (nearest_school_km > 8 or nearest_hospital_km > 20)
    isolated = nearest_school_km > 8 or nearest_hospital_km > 20

    if category == "Roads" and severely_underserved:
        return 90
    if category in ("Education", "Healthcare") and isolated:
        return 75
    if category in ("Digital", "Employment"):
        return 50
    return 40


def calculate_drfi_score(block: dict, category: str, submissions_for_block: list) -> dict:
    """Compute all 7 DRFI components + final weighted score for a block+category pair."""
    citizen_demand = _citizen_demand_score(submissions_for_block)
    demographic_need = _demographic_need_score(block, category)
    infrastructure_gap = _infrastructure_gap_score(block, category)
    equity = _equity_score(block)
    plan_alignment = _plan_alignment_score(block)
    cost_effectiveness = _cost_effectiveness_score(block, category)
    cascading_impact = _cascading_impact_score(block, category)

    drfi_score = (
        citizen_demand * COMPONENT_WEIGHTS["citizen_demand"]
        + demographic_need * COMPONENT_WEIGHTS["demographic_need"]
        + infrastructure_gap * COMPONENT_WEIGHTS["infrastructure_gap"]
        + equity * COMPONENT_WEIGHTS["equity"]
        + plan_alignment * COMPONENT_WEIGHTS["plan_alignment"]
        + cost_effectiveness * COMPONENT_WEIGHTS["cost_effectiveness"]
        + cascading_impact * COMPONENT_WEIGHTS["cascading_impact"]
    )

    return {
        "block_name": block.get("block_name"),
        "category": category,
        "citizen_demand_score": round(citizen_demand, 2),
        "demographic_need_score": round(demographic_need, 2),
        "infrastructure_gap_score": round(infrastructure_gap, 2),
        "equity_score": round(equity, 2),
        "plan_alignment_score": round(plan_alignment, 2),
        "cost_effectiveness_score": round(cost_effectiveness, 2),
        "cascading_impact_score": round(cascading_impact, 2),
        "drfi_score": round(_clamp(drfi_score), 2),
    }


def detect_counter_narrative(block: dict, category: str, submission_count: int):
    """Returns a dict with flag+note if submissions contradict existing block infrastructure, else None."""
    if category == "Healthcare" and (block.get("nearest_hospital_km") or 999) < 2.0 and submission_count > 10:
        return {
            "flag": True,
            "note": (
                f"Hospital exists {block.get('nearest_hospital_km')}km away. "
                "Issue may be quality/access, not new infrastructure."
            ),
        }
    if category == "Education" and (block.get("school_capacity_used") or 100) < 60 and submission_count > 5:
        return {
            "flag": True,
            "note": (
                f"Nearby school at {block.get('school_capacity_used')}% capacity. "
                "Consider improving existing rather than building new."
            ),
        }
    return None


def detect_silent_needs(blocks: list, all_submissions: list) -> list:
    """Yields blocks with severe demographic deficit but very few submissions."""
    results = []
    for block in blocks:
        block_name = block.get("block_name")
        block_submissions = [s for s in all_submissions if s.get("location_mentioned") == block_name]
        sc_st_percent = block.get("sc_st_percent") or 0
        nearest_school_km = block.get("nearest_school_km") or 0

        if len(block_submissions) < 3 and sc_st_percent > 60 and nearest_school_km > 8:
            results.append(
                {
                    "block_name": block_name,
                    "issue": (
                        f"High SC/ST population ({sc_st_percent}%), school {nearest_school_km}km away, "
                        f"only {len(block_submissions)} submissions — possible silent need"
                    ),
                    "submission_count": len(block_submissions),
                    "sc_st_percent": sc_st_percent,
                    "nearest_school_km": nearest_school_km,
                }
            )
    return results
