"""Core calculation engine for the compensation planning dashboard.

Every formula, score, and recommendation lives here as small, pure(ish)
functions so the model can be unit tested (see tests/test_calc.py) without a
Flask app or a browser. `app.py` is a thin layer that loads data, calls
`compute_all`, and renders it.

Nothing here reads or writes protected characteristics (race, age, gender,
disability, etc.) - see docs/ASSUMPTIONS.md for the full list of governance
guardrails this module intentionally does NOT cross.
"""

from __future__ import annotations

import datetime
from collections import defaultdict

POSITION_CATEGORIES = [
    "Below Minimum",
    "Low in Range",
    "Appropriately Positioned",
    "High in Range",
    "Above Maximum",
]

FLIGHT_RISK_RATINGS = ["Low", "Moderate", "High", "Critical"]

PRIORITY_LABELS = {
    1: "Below range minimum",
    2: "High performer significantly underpositioned",
    3: "High flight risk",
    4: "Business-critical / difficult-to-replace role",
    5: "Internal pay-equity concern",
    6: "Delayed adjustment / strong performer fallen behind",
    7: "Standard / monitor",
}


# ---------------------------------------------------------------------------
# Dates
# ---------------------------------------------------------------------------

def parse_date(value):
    if value is None or value == "":
        return None
    if isinstance(value, datetime.date):
        return value
    return datetime.datetime.strptime(str(value).strip(), "%Y-%m-%d").date()


def years_between(start, as_of):
    if start is None:
        return None
    return (as_of - start).days / 365.25


def months_between(start, as_of):
    if start is None:
        return None
    return (as_of - start).days / 30.4375


# ---------------------------------------------------------------------------
# 1. Basic position formulas
# ---------------------------------------------------------------------------

def salary_position_pct(current_salary, range_min, range_max):
    """(Current Salary - Range Minimum) / (Range Maximum - Range Minimum)."""
    span = range_max - range_min
    if span <= 0:
        return None
    return (current_salary - range_min) / span


def compa_ratio(current_salary, range_mid):
    """Current Salary / Range Midpoint."""
    if not range_mid:
        return None
    return current_salary / range_mid


# ---------------------------------------------------------------------------
# 2. Combined performance score
# ---------------------------------------------------------------------------

def normalize_supervisor(rating, scale_max):
    if rating is None:
        return None
    return max(0.0, min(100.0, (rating / scale_max) * 100.0))


def normalize_objective(score, scale_max):
    if score is None:
        return None
    return max(0.0, min(100.0, (score / scale_max) * 100.0))


def performance_tier(combined_score, tiers):
    if combined_score is None:
        return None
    for tier in tiers:
        if combined_score >= tier["floor"]:
            return tier["name"]
    return tiers[-1]["name"]


def combined_performance(supervisor_rating, objective_score, config):
    perf_cfg = config["performance"]
    sup_norm = normalize_supervisor(supervisor_rating, perf_cfg["supervisor_scale_max"])
    obj_norm = normalize_objective(objective_score, perf_cfg["objective_scale_max"])

    result = {
        "supervisor_normalized": sup_norm,
        "objective_normalized": obj_norm,
        "combined_score": None,
        "tier": None,
        "divergence_flag": False,
        "divergence_points": None,
        "divergence_direction": None,
        "data_incomplete": sup_norm is None or obj_norm is None,
    }
    if sup_norm is None or obj_norm is None:
        # Fall back to whichever single score exists so the record isn't
        # silently dropped, but data_incomplete stays True for review.
        available = [v for v in (sup_norm, obj_norm) if v is not None]
        result["combined_score"] = available[0] if available else None
    else:
        w_sup = perf_cfg["weight_supervisor"]
        w_obj = perf_cfg["weight_objective"]
        total_w = w_sup + w_obj or 1.0
        result["combined_score"] = (sup_norm * w_sup + obj_norm * w_obj) / total_w

        diff = sup_norm - obj_norm
        result["divergence_points"] = abs(diff)
        if abs(diff) >= perf_cfg["divergence_flag_points"]:
            result["divergence_flag"] = True
            result["divergence_direction"] = (
                "Supervisor rating much higher than objective metrics"
                if diff > 0
                else "Objective metrics much higher than supervisor rating"
            )

    result["tier"] = performance_tier(result["combined_score"], perf_cfg["tiers"])
    return result


# ---------------------------------------------------------------------------
# 3. Expected position band (this is the "not everyone belongs at midpoint" model)
# ---------------------------------------------------------------------------

def tenure_shift_points(tenure_years, tenure_shift_cfg):
    if tenure_years is None:
        return 0.0
    for rule in tenure_shift_cfg:
        if rule["max_years"] is None or tenure_years <= rule["max_years"]:
            return rule["shift"]
    return tenure_shift_cfg[-1]["shift"]


def expected_band(tier, tenure_years, critical_role, config):
    """Returns (center, low, high) as compa-ratio fractions (1.00 = midpoint).

    The center shifts up for stronger performers, longer tenure, and
    critical/hard-to-replace roles - reflecting that pay position should be
    earned, not handed out uniformly at the midpoint.
    """
    pm_cfg = config["position_model"]
    perf_shift = pm_cfg["performance_shift_pts"].get(tier, 0) / 100.0
    ten_shift = tenure_shift_points(tenure_years, pm_cfg["tenure_shift_pts"]) / 100.0
    crit_shift = (pm_cfg["critical_role_shift_pts"] / 100.0) if critical_role else 0.0
    center = 1.0 + perf_shift + ten_shift + crit_shift
    half = pm_cfg["band_half_width_pts"] / 100.0
    return center, center - half, center + half


def salary_position_category(current_salary, range_min, range_max, ratio, band_low, band_high):
    if current_salary < range_min:
        return "Below Minimum"
    if current_salary > range_max:
        return "Above Maximum"
    if ratio is None:
        return "Appropriately Positioned"
    if ratio < band_low:
        return "Low in Range"
    if ratio > band_high:
        return "High in Range"
    return "Appropriately Positioned"


# ---------------------------------------------------------------------------
# 4. Internal-equity peer scan (relative-to-peers, computed - separate from
#    the manual HR-entered internal_equity_flag)
# ---------------------------------------------------------------------------

def internal_equity_scan(records, config):
    """Flags employees paid materially below the average compa-ratio of
    peers in the same department + job title, when their performance does
    not explain the gap. This augments (never replaces) the manual
    internal_equity_flag field HR can set directly.

    Mutates each record dict in place, adding:
      computed_equity_gap_pts, computed_equity_concern
    """
    eq_cfg = config.get("equity", {
        "gap_threshold_pts": 8,
        "min_group_size": 2,
    })
    groups = defaultdict(list)
    for r in records:
        # Level is part of the key so a Level I and a Level III in the same
        # job family are never compared as if they were pay peers.
        key = (r["department"], r["job_title"], r.get("level"))
        groups[key].append(r)

    for key, group in groups.items():
        ratios = [r["compa_ratio"] for r in group if r["compa_ratio"] is not None]
        if len(group) < eq_cfg.get("min_group_size", 2) or not ratios:
            for r in group:
                r["computed_equity_gap_pts"] = 0.0
                r["computed_equity_concern"] = False
                r["peer_group_avg_compa_ratio"] = None
            continue
        avg_ratio = sum(ratios) / len(ratios)
        for r in group:
            if r["compa_ratio"] is None:
                r["computed_equity_gap_pts"] = 0.0
                r["computed_equity_concern"] = False
                r["peer_group_avg_compa_ratio"] = avg_ratio
                continue
            gap_pts = (avg_ratio - r["compa_ratio"]) * 100
            r["peer_group_avg_compa_ratio"] = avg_ratio
            r["computed_equity_gap_pts"] = gap_pts
            # Low performers being paid below the peer average is not, by
            # itself, an equity problem - only flag Solid-or-better performers.
            low_tier = r["performance"]["tier"] in ("Developing", "Low")
            r["computed_equity_concern"] = bool(
                gap_pts >= eq_cfg.get("gap_threshold_pts", 8) and not low_tier
            )
    return records


# ---------------------------------------------------------------------------
# 5. Flight risk
# ---------------------------------------------------------------------------

def _bucket(value, breakpoints):
    """breakpoints: list of (max_value_inclusive_or_None, score)."""
    if value is None:
        return breakpoints[0][1]
    for limit, score in breakpoints:
        if limit is None or value <= limit:
            return score
    return breakpoints[-1][1]


def flight_risk(record, config):
    fr_cfg = config["flight_risk"]
    weights = fr_cfg["weights"]

    category = record["position_category"]
    ratio = record["compa_ratio"]
    band_low = record["band_low"]
    tier = record["performance"]["tier"]
    months_since_raise = record["months_since_raise"]
    tenure_years = record["tenure_years"]
    market_demand = (record.get("market_demand") or "Low").strip().title()
    retention_notes = (record.get("retention_notes") or "").strip()
    high_perf = tier in config["raise_model"]["high_performer_tiers"]

    comp_position_risk = {
        "Below Minimum": 100,
        "Low in Range": 65,
        "Appropriately Positioned": 25,
        "High in Range": 10,
        "Above Maximum": 5,
    }.get(category, 25)

    if ratio is None or band_low is None or ratio >= band_low:
        compa_gap_risk = 0
    else:
        compa_gap_risk = max(0.0, min(100.0, (band_low - ratio) * 400))

    time_since_raise_risk = _bucket(
        months_since_raise,
        [(12, 10), (18, 30), (24, 55), (36, 75), (None, 95)],
    )

    if high_perf and category in ("Below Minimum", "Low in Range"):
        performance_pay_mismatch_risk = 90
    elif high_perf and category == "Appropriately Positioned":
        performance_pay_mismatch_risk = 30
    else:
        performance_pay_mismatch_risk = 10

    tenure_curve_risk = _bucket(
        tenure_years,
        [(1, 25), (3, 55), (7, 35), (None, 20)],
    )

    market_demand_risk = {"Low": 15, "Medium": 45, "High": 80}.get(market_demand, 15)
    retention_notes_risk = 70 if retention_notes else 15

    components = {
        "comp_position": comp_position_risk,
        "compa_ratio_gap": compa_gap_risk,
        "time_since_raise": time_since_raise_risk,
        "performance_pay_mismatch": performance_pay_mismatch_risk,
        "tenure_curve": tenure_curve_risk,
        "market_demand": market_demand_risk,
        "retention_notes": retention_notes_risk,
    }

    overall = sum(components[k] * weights[k] for k in weights) / (sum(weights.values()) or 1.0)

    # Governance requirement: keep what is measured (compensation + tenure
    # data) visibly separate from what is judgment-based (manager-entered
    # market demand / retention notes).
    measurable_keys = ["comp_position", "compa_ratio_gap", "time_since_raise",
                       "performance_pay_mismatch", "tenure_curve"]
    subjective_keys = ["market_demand", "retention_notes"]
    measurable_w = sum(weights[k] for k in measurable_keys) or 1.0
    subjective_w = sum(weights[k] for k in subjective_keys) or 1.0
    measurable_score = sum(components[k] * weights[k] for k in measurable_keys) / measurable_w
    subjective_score = sum(components[k] * weights[k] for k in subjective_keys) / subjective_w

    bands = fr_cfg["bands"]
    if overall <= bands["low_max"]:
        rating = "Low"
    elif overall <= bands["moderate_max"]:
        rating = "Moderate"
    elif overall <= bands["high_max"]:
        rating = "High"
    else:
        rating = "Critical"

    return {
        "score": round(overall, 1),
        "rating": rating,
        "measurable_score": round(measurable_score, 1),
        "subjective_score": round(subjective_score, 1),
        "components": components,
    }


# ---------------------------------------------------------------------------
# 6. Raise recommendation + prioritization
# ---------------------------------------------------------------------------

def _matched_priority_reasons(record, config):
    reasons = []
    rm = config["raise_model"]
    tier = record["performance"]["tier"]
    high_perf = tier in rm["high_performer_tiers"]
    category = record["position_category"]
    ratio = record["compa_ratio"]
    band_low = record["band_low"]

    if record["current_salary"] < record["range_min"]:
        reasons.append((1, PRIORITY_LABELS[1]))

    if (
        high_perf
        and category in ("Below Minimum", "Low in Range")
        and ratio is not None
        and band_low is not None
        and (band_low - ratio) * 100 >= rm["significant_gap_pts"]
    ):
        reasons.append((2, PRIORITY_LABELS[2]))

    if record["flight_risk"]["rating"] in ("High", "Critical"):
        reasons.append((3, PRIORITY_LABELS[3]))

    if record.get("critical_role"):
        reasons.append((4, PRIORITY_LABELS[4]))

    if record.get("equity_concern"):
        reasons.append((5, PRIORITY_LABELS[5]))

    if (
        high_perf
        and record["months_since_raise"] is not None
        and record["months_since_raise"] >= rm["long_cycle_months"]
        and category != "Above Maximum"
    ):
        reasons.append((6, PRIORITY_LABELS[6]))

    return reasons


def raise_recommendation(record, config):
    rm = config["raise_model"]
    reasons = _matched_priority_reasons(record, config)
    priority = min((r[0] for r in reasons), default=7)
    reason_labels = sorted({r[1] for r in reasons})

    target_center = record["band_center"]
    target_salary = target_center * record["range_mid"]

    if record.get("equity_concern") and record.get("peer_group_avg_compa_ratio"):
        equity_target = record["peer_group_avg_compa_ratio"] * record["range_mid"]
        target_salary = max(target_salary, equity_target)

    if record["current_salary"] < record["range_min"]:
        target_salary = max(target_salary, record["range_min"] * (1 + rm["below_min_buffer_pct"] / 100.0))

    raw_gap_pct = (target_salary - record["current_salary"]) / record["current_salary"] * 100.0
    gap_pct = max(0.0, raw_gap_pct)

    high_perf = record["performance"]["tier"] in rm["high_performer_tiers"]
    flight_high = record["flight_risk"]["rating"] in ("High", "Critical")

    exception_reasons = []
    if record["current_salary"] < record["range_min"]:
        exception_reasons.append("Employee is below the salary range minimum")
    if record.get("equity_concern") and record.get("computed_equity_gap_pts", 0) >= 2 * config.get(
        "equity", {}
    ).get("gap_threshold_pts", 8):
        exception_reasons.append("Severe internal pay-equity gap versus peers in the same role")
    if high_perf and flight_high:
        exception_reasons.append("High performer with significant flight risk")
    if record.get("critical_role") and gap_pct > rm["standard_cap_pct"]:
        exception_reasons.append("Business-critical / difficult-to-replace role")
    if (record.get("market_demand") or "").strip().title() == "High" and gap_pct > rm["standard_cap_pct"]:
        exception_reasons.append("Market pay for this skill set has moved substantially")
    if priority == 6 and gap_pct > rm["standard_cap_pct"]:
        exception_reasons.append("A delayed adjustment cycle has created a significant compensation gap")

    exception_eligible = len(exception_reasons) > 0
    cap = rm["exception_cap_pct"] if exception_eligible else rm["standard_cap_pct"]

    immediate_pct = min(gap_pct, cap)
    remaining_after_immediate = gap_pct - immediate_pct
    phased = remaining_after_immediate > 0.01

    phase2_pct = 0.0
    phase2_timing_months = None
    remaining_after_phase2 = 0.0
    if phased:
        phase2_cap = rm["exception_cap_pct"] if exception_eligible else rm["standard_cap_pct"]
        phase2_pct = min(remaining_after_immediate, phase2_cap)
        phase2_timing_months = 6 if exception_eligible else 12
        remaining_after_phase2 = remaining_after_immediate - phase2_pct

    immediate_amount = record["current_salary"] * immediate_pct / 100.0
    proposed_new_salary = record["current_salary"] + immediate_amount
    new_compa_ratio = compa_ratio(proposed_new_salary, record["range_mid"])
    new_position_pct = salary_position_pct(proposed_new_salary, record["range_min"], record["range_max"])
    new_position_category = salary_position_category(
        proposed_new_salary, record["range_min"], record["range_max"],
        new_compa_ratio, record["band_low"], record["band_high"],
    )

    if reason_labels:
        justification = (
            f"Priority {priority} ({PRIORITY_LABELS.get(priority, '')}). "
            f"Matched factors: {'; '.join(reason_labels)}."
        )
    else:
        justification = "No urgent priority factors matched; monitor at next standard review cycle."
    if exception_eligible:
        justification += " EXCEPTION (>10%): " + "; ".join(exception_reasons) + "."
    if phased:
        justification += (
            f" Gap exceeds the single-adjustment cap; remainder proposed as a phased increase "
            f"of ~{phase2_pct:.1f}% in ~{phase2_timing_months} months."
        )
        if remaining_after_phase2 > 0.5:
            justification += (
                f" Even after two phases, ~{remaining_after_phase2:.1f}% of the gap would remain - "
                f"schedule a third-phase review rather than exceeding the 15% single-adjustment cap."
            )

    requires_review = bool(
        exception_eligible
        or record.get("equity_concern")
        or record["performance"].get("data_incomplete")
        or immediate_pct > rm["standard_cap_pct"]
    )
    requires_review_reasons = []
    if exception_eligible:
        requires_review_reasons.append("Raise exceeds the standard 10% cap")
    if record.get("equity_concern"):
        requires_review_reasons.append("Pay-equity concern - route to HR/compensation for review, not a legal determination")
    if record["performance"].get("data_incomplete"):
        requires_review_reasons.append("Incomplete supervisor or objective performance data")

    return {
        "priority_tier": priority,
        "priority_label": PRIORITY_LABELS.get(priority, ""),
        "matched_reasons": reason_labels,
        "target_salary": target_salary,
        "full_recommended_pct": round(gap_pct, 2),
        "immediate_pct": round(immediate_pct, 2),
        "immediate_amount": round(immediate_amount, 2),
        "proposed_new_salary": round(proposed_new_salary, 2),
        "new_compa_ratio": new_compa_ratio,
        "new_position_pct": new_position_pct,
        "new_position_category": new_position_category,
        "phased": phased,
        "phase2_pct": round(phase2_pct, 2),
        "phase2_timing_months": phase2_timing_months,
        "remaining_gap_after_phase2_pct": round(remaining_after_phase2, 2),
        "exception_flag": exception_eligible,
        "exception_reasons": exception_reasons,
        "business_justification": justification,
        "requires_review": requires_review,
        "requires_review_reasons": requires_review_reasons,
        "adjustment_timing": "Phased" if phased else ("Immediate" if immediate_pct > 0 else "None recommended"),
    }


# ---------------------------------------------------------------------------
# 7. Per-employee compute pipeline
# ---------------------------------------------------------------------------

def compute_employee(raw, config, as_of):
    r = dict(raw)
    r["hire_date"] = parse_date(raw.get("hire_date"))
    r["last_raise_date"] = parse_date(raw.get("last_raise_date"))
    r["current_salary"] = float(raw["current_salary"])
    r["range_min"] = float(raw["range_min"])
    r["range_mid"] = float(raw["range_mid"])
    r["range_max"] = float(raw["range_max"])
    r["critical_role"] = str(raw.get("critical_role", "N")).strip().upper() == "Y"
    r["internal_equity_flag"] = str(raw.get("internal_equity_flag", "N")).strip().upper() == "Y"
    sup = raw.get("supervisor_rating")
    obj = raw.get("objective_score")
    r["supervisor_rating"] = float(sup) if sup not in (None, "") else None
    r["objective_score"] = float(obj) if obj not in (None, "") else None

    r["tenure_years"] = years_between(r["hire_date"], as_of)
    raise_anchor = r["last_raise_date"] or r["hire_date"]
    r["months_since_raise"] = months_between(raise_anchor, as_of)

    r["position_pct"] = salary_position_pct(r["current_salary"], r["range_min"], r["range_max"])
    r["compa_ratio"] = compa_ratio(r["current_salary"], r["range_mid"])

    r["performance"] = combined_performance(r["supervisor_rating"], r["objective_score"], config)

    center, low, high = expected_band(r["performance"]["tier"], r["tenure_years"], r["critical_role"], config)
    r["band_center"] = center
    r["band_low"] = low
    r["band_high"] = high

    r["position_category"] = salary_position_category(
        r["current_salary"], r["range_min"], r["range_max"], r["compa_ratio"], low, high
    )

    missing_fields = [
        name for name in ("supervisor_rating", "objective_score", "hire_date")
        if r.get(name) is None
    ]
    r["data_quality_flags"] = missing_fields

    return r


def compute_all(raw_employees, config, as_of=None):
    """Runs the full per-employee pipeline plus the peer equity scan and
    flight-risk/raise models, which need the full roster or a fully
    populated record to run. Returns the list of fully computed records.
    """
    as_of = as_of or datetime.date.today()
    records = [compute_employee(e, config, as_of) for e in raw_employees]

    internal_equity_scan(records, config)
    for r in records:
        r["equity_concern"] = bool(r["internal_equity_flag"] or r.get("computed_equity_concern"))

    for r in records:
        r["flight_risk"] = flight_risk(r, config)

    for r in records:
        r["raise"] = raise_recommendation(r, config)

    return records


# ---------------------------------------------------------------------------
# 8. Budget scenarios
# ---------------------------------------------------------------------------

def _sort_key(r):
    return (
        r["raise"]["priority_tier"],
        -r["flight_risk"]["score"],
        -r["raise"]["full_recommended_pct"],
    )


def apply_scenario(records, config, scenario_name="no_budget", custom_budget=None):
    """Adds funded_pct / funded_amount / deferred_pct / deferred_amount /
    remaining_gap_pct / scenario_excluded to each record (mutates + returns).

    Scenarios:
      no_budget     - fund every employee's full immediate (phase 1) recommendation
      fixed_budget  - custom_budget dollars, allocated by priority order
      conservative / moderate / aggressive - presets from config.scenarios
    """
    scenarios_cfg = config["scenarios"]
    ordered = sorted(records, key=_sort_key)

    if scenario_name == "no_budget":
        for r in ordered:
            r["scenario_excluded"] = False
            r["funded_pct"] = r["raise"]["immediate_pct"]
            r["funded_amount"] = r["raise"]["immediate_amount"]
            r["deferred_pct"] = 0.0
            r["deferred_amount"] = 0.0
        finalize_scenario_fields(ordered)
        return ordered

    if scenario_name == "fixed_budget":
        budget = custom_budget or 0.0
        tier_cutoff = None
        max_individual_pct = None
    else:
        preset = scenarios_cfg[scenario_name]
        tier_cutoff = preset.get("tier_cutoff")
        max_individual_pct = preset.get("max_individual_pct")
        eligible_cost = sum(
            r["current_salary"] * min(r["raise"]["immediate_pct"], max_individual_pct or 100) / 100.0
            for r in ordered
            if tier_cutoff is None or r["raise"]["priority_tier"] <= tier_cutoff
        )
        budget = eligible_cost * preset.get("budget_multiplier", 1.0)

    remaining_budget = budget
    for r in ordered:
        eligible = tier_cutoff is None or r["raise"]["priority_tier"] <= tier_cutoff
        r["scenario_excluded"] = not eligible
        if not eligible:
            r["funded_pct"] = 0.0
            r["funded_amount"] = 0.0
            r["deferred_pct"] = r["raise"]["immediate_pct"]
            r["deferred_amount"] = r["raise"]["immediate_amount"]
            continue

        target_pct = r["raise"]["immediate_pct"]
        if max_individual_pct is not None:
            target_pct = min(target_pct, max_individual_pct)
        target_amount = r["current_salary"] * target_pct / 100.0

        if remaining_budget >= target_amount:
            r["funded_pct"] = round(target_pct, 2)
            r["funded_amount"] = round(target_amount, 2)
            remaining_budget -= target_amount
        elif remaining_budget > 0:
            funded_amount = remaining_budget
            r["funded_pct"] = round(funded_amount / r["current_salary"] * 100.0, 2)
            r["funded_amount"] = round(funded_amount, 2)
            remaining_budget = 0.0
        else:
            r["funded_pct"] = 0.0
            r["funded_amount"] = 0.0

        r["deferred_pct"] = round(target_pct - r["funded_pct"], 2)
        r["deferred_amount"] = round(target_amount - r["funded_amount"], 2)

    finalize_scenario_fields(ordered)
    return ordered


def finalize_scenario_fields(records):
    for r in records:
        new_salary = r["current_salary"] + r["funded_amount"]
        r["scenario_new_salary"] = round(new_salary, 2)
        r["scenario_new_compa_ratio"] = compa_ratio(new_salary, r["range_mid"])
        r["scenario_new_position_pct"] = salary_position_pct(new_salary, r["range_min"], r["range_max"])
        r["scenario_new_position_category"] = salary_position_category(
            new_salary, r["range_min"], r["range_max"],
            r["scenario_new_compa_ratio"], r["band_low"], r["band_high"],
        )
        full_target = r["raise"]["target_salary"]
        r["remaining_gap_amount"] = round(max(0.0, full_target - new_salary), 2)
        r["remaining_gap_pct"] = round(
            max(0.0, (full_target - new_salary) / new_salary * 100.0) if new_salary else 0.0, 2
        )


# ---------------------------------------------------------------------------
# 9. Dashboard summaries
# ---------------------------------------------------------------------------

def summarize(records, config):
    total_current_payroll = sum(r["current_salary"] for r in records)
    total_funded_budget = sum(r["funded_amount"] for r in records)
    total_full_recommended = sum(r["raise"]["immediate_amount"] for r in records)
    total_deferred = sum(r["deferred_amount"] for r in records)

    low_threshold = config["compa_ratio_low_threshold"]

    by_dept = defaultdict(lambda: {"headcount": 0, "current_payroll": 0.0, "funded_amount": 0.0, "full_recommended_amount": 0.0})
    for r in records:
        d = by_dept[r["department"]]
        d["headcount"] += 1
        d["current_payroll"] += r["current_salary"]
        d["funded_amount"] += r["funded_amount"]
        d["full_recommended_amount"] += r["raise"]["immediate_amount"]

    by_tier = defaultdict(lambda: {"headcount": 0, "funded_amount": 0.0})
    for r in records:
        t = by_tier[r["performance"]["tier"] or "Unknown"]
        t["headcount"] += 1
        t["funded_amount"] += r["funded_amount"]

    by_priority = defaultdict(lambda: {"headcount": 0, "funded_amount": 0.0, "label": ""})
    for r in records:
        p = by_priority[r["raise"]["priority_tier"]]
        p["headcount"] += 1
        p["funded_amount"] += r["funded_amount"]
        p["label"] = r["raise"]["priority_label"]

    immediate_cost = sum(r["funded_amount"] for r in records if not r["raise"]["phased"])
    phased_cost = sum(r["funded_amount"] for r in records if r["raise"]["phased"])

    def compa_bucket(ratio):
        if ratio is None:
            return "Unknown"
        if ratio < 0.85:
            return "<85%"
        if ratio < 0.95:
            return "85-95%"
        if ratio < 1.05:
            return "95-105%"
        if ratio < 1.15:
            return "105-115%"
        return "115%+"

    before_compa_dist = defaultdict(int)
    after_compa_dist = defaultdict(int)
    for r in records:
        before_compa_dist[compa_bucket(r["compa_ratio"])] += 1
        after_compa_dist[compa_bucket(r["scenario_new_compa_ratio"])] += 1

    before_position_dist = defaultdict(int)
    after_position_dist = defaultdict(int)
    for r in records:
        before_position_dist[r["position_category"]] += 1
        after_position_dist[r["scenario_new_position_category"]] += 1

    return {
        "headcount": len(records),
        "total_current_payroll": total_current_payroll,
        "total_funded_budget": total_funded_budget,
        "total_full_recommended_budget": total_full_recommended,
        "total_deferred": total_deferred,
        "overall_payroll_increase_pct": (
            total_funded_budget / total_current_payroll * 100.0 if total_current_payroll else 0.0
        ),
        "count_below_min": sum(1 for r in records if r["position_category"] == "Below Minimum"),
        "count_above_max": sum(1 for r in records if r["position_category"] == "Above Maximum"),
        "count_compa_below_threshold": sum(
            1 for r in records if r["compa_ratio"] is not None and r["compa_ratio"] < low_threshold
        ),
        "count_high_critical_flight_risk": sum(
            1 for r in records if r["flight_risk"]["rating"] in ("High", "Critical")
        ),
        "count_equity_concerns": sum(1 for r in records if r["equity_concern"]),
        "count_requires_review": sum(1 for r in records if r["raise"]["requires_review"]),
        "count_data_quality_issues": sum(1 for r in records if r["data_quality_flags"]),
        "by_department": dict(by_dept),
        "by_performance_tier": dict(by_tier),
        "by_priority": dict(by_priority),
        "immediate_cost": immediate_cost,
        "phased_cost": phased_cost,
        "before_compa_distribution": dict(before_compa_dist),
        "after_compa_distribution": dict(after_compa_dist),
        "before_position_distribution": dict(before_position_dist),
        "after_position_distribution": dict(after_position_dist),
    }
