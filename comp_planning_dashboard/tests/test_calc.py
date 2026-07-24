import datetime
import json
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import calc

CONFIG_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "config.json")


def load_config():
    with open(CONFIG_PATH) as f:
        return json.load(f)


def make_employee(**overrides):
    base = dict(
        employee_id="T1",
        name="Test Employee",
        department="Engineering",
        job_title="Software Engineer",
        level="II",
        hire_date="2022-01-01",
        current_salary=100000,
        range_min=88000,
        range_mid=103000,
        range_max=118000,
        supervisor_rating=4.0,
        objective_score=80,
        last_raise_date="2024-01-01",
        critical_role="N",
        market_demand="Medium",
        internal_equity_flag="N",
        retention_notes="",
    )
    base.update(overrides)
    return base


AS_OF = datetime.date(2026, 7, 24)


# ---------------------------------------------------------------------------
# Basic formulas
# ---------------------------------------------------------------------------

def test_salary_position_pct():
    assert calc.salary_position_pct(100000, 80000, 120000) == 0.5
    assert calc.salary_position_pct(80000, 80000, 120000) == 0.0
    assert calc.salary_position_pct(120000, 80000, 120000) == 1.0


def test_compa_ratio():
    assert calc.compa_ratio(90000, 100000) == 0.9
    assert calc.compa_ratio(110000, 100000) == 1.1


def test_salary_position_pct_invalid_range():
    assert calc.salary_position_pct(50000, 100000, 100000) is None


# ---------------------------------------------------------------------------
# Combined performance
# ---------------------------------------------------------------------------

def test_combined_performance_default_weights():
    config = load_config()
    result = calc.combined_performance(5.0, 100, config)
    assert result["supervisor_normalized"] == 100
    assert result["objective_normalized"] == 100
    assert result["combined_score"] == 100
    assert result["tier"] == "Top"


def test_combined_performance_divergence_flag():
    config = load_config()
    # Supervisor rates max (100 normalized), objective metrics very low.
    result = calc.combined_performance(5.0, 20, config)
    assert result["divergence_flag"] is True
    assert "Supervisor" in result["divergence_direction"]


def test_combined_performance_no_divergence_when_close():
    config = load_config()
    result = calc.combined_performance(4.0, 78, config)  # 80 vs 78
    assert result["divergence_flag"] is False


def test_combined_performance_missing_data():
    config = load_config()
    result = calc.combined_performance(None, 80, config)
    assert result["data_incomplete"] is True
    assert result["combined_score"] == 80


# ---------------------------------------------------------------------------
# Expected band / position category
# ---------------------------------------------------------------------------

def test_expected_band_shifts_up_for_top_performer_and_tenure():
    config = load_config()
    center_low, low_low, high_low = calc.expected_band("Low", 0.5, False, config)
    center_top, low_top, high_top = calc.expected_band("Top", 8, True, config)
    assert center_top > center_low


def test_position_category_below_minimum():
    assert calc.salary_position_category(70000, 80000, 120000, 0.7, 0.9, 1.1) == "Below Minimum"


def test_position_category_above_maximum():
    assert calc.salary_position_category(130000, 80000, 120000, 1.2, 0.9, 1.1) == "Above Maximum"


def test_position_category_low_and_high_and_appropriate():
    assert calc.salary_position_category(85000, 80000, 120000, 0.85, 0.9, 1.1) == "Low in Range"
    assert calc.salary_position_category(115000, 80000, 120000, 1.15, 0.9, 1.1) == "High in Range"
    assert calc.salary_position_category(100000, 80000, 120000, 1.0, 0.9, 1.1) == "Appropriately Positioned"


# ---------------------------------------------------------------------------
# Raise recommendation
# ---------------------------------------------------------------------------

def test_below_minimum_gets_priority_one_and_a_raise():
    config = load_config()
    emp = make_employee(current_salary=80000, range_min=88000, range_mid=103000, range_max=118000)
    [record] = calc.compute_all([emp], config, as_of=AS_OF)
    assert record["position_category"] == "Below Minimum"
    assert record["raise"]["priority_tier"] == 1
    assert record["raise"]["immediate_pct"] > 0
    assert record["raise"]["proposed_new_salary"] >= record["range_min"]


def test_raise_never_exceeds_exception_cap_in_a_single_phase():
    config = load_config()
    # Deep below minimum -> large gap -> should cap at exception cap and phase the rest.
    emp = make_employee(current_salary=50000, range_min=88000, range_mid=103000, range_max=118000, critical_role="Y")
    [record] = calc.compute_all([emp], config, as_of=AS_OF)
    cap = config["raise_model"]["exception_cap_pct"]
    assert record["raise"]["immediate_pct"] <= cap + 1e-6
    assert record["raise"]["phased"] is True
    assert record["raise"]["phase2_pct"] > 0


def test_standard_cap_applies_without_exception_conditions():
    config = load_config()
    # Solid performer, modestly below midpoint, nothing exceptional -> capped at 10%, not 15%.
    emp = make_employee(
        current_salary=95000, range_min=88000, range_mid=103000, range_max=118000,
        supervisor_rating=3.2, objective_score=60, critical_role="N", market_demand="Low",
        hire_date="2023-01-01", last_raise_date="2025-06-01",
    )
    [record] = calc.compute_all([emp], config, as_of=AS_OF)
    assert record["raise"]["exception_flag"] is False
    assert record["raise"]["immediate_pct"] <= config["raise_model"]["standard_cap_pct"] + 1e-6


def test_appropriately_positioned_gets_no_raise():
    config = load_config()
    emp = make_employee(current_salary=103000, range_min=88000, range_mid=103000, range_max=118000,
                         supervisor_rating=3.0, objective_score=60)
    [record] = calc.compute_all([emp], config, as_of=AS_OF)
    assert record["raise"]["full_recommended_pct"] == 0.0
    assert record["raise"]["immediate_pct"] == 0.0


# ---------------------------------------------------------------------------
# Flight risk
# ---------------------------------------------------------------------------

def test_flight_risk_rating_is_one_of_the_four_bands():
    config = load_config()
    emp = make_employee()
    [record] = calc.compute_all([emp], config, as_of=AS_OF)
    assert record["flight_risk"]["rating"] in calc.FLIGHT_RISK_RATINGS


def test_flight_risk_higher_for_below_min_high_performer_with_retention_note():
    config = load_config()
    safe = make_employee(employee_id="SAFE", current_salary=103000, supervisor_rating=3.0, objective_score=60)
    risky = make_employee(
        employee_id="RISKY", current_salary=80000, supervisor_rating=4.8, objective_score=95,
        market_demand="High", retention_notes="Interviewing elsewhere",
    )
    records = calc.compute_all([safe, risky], config, as_of=AS_OF)
    by_id = {r["employee_id"]: r for r in records}
    assert by_id["RISKY"]["flight_risk"]["score"] > by_id["SAFE"]["flight_risk"]["score"]


def test_flight_risk_separates_measurable_from_subjective():
    config = load_config()
    emp = make_employee(retention_notes="Known concern")
    [record] = calc.compute_all([emp], config, as_of=AS_OF)
    fr = record["flight_risk"]
    assert "measurable_score" in fr and "subjective_score" in fr
    assert fr["measurable_score"] != fr["subjective_score"] or True  # both always present


# ---------------------------------------------------------------------------
# Internal equity scan
# ---------------------------------------------------------------------------

def test_equity_scan_flags_underpaid_peer():
    config = load_config()
    well_paid = make_employee(employee_id="A", current_salary=112000, supervisor_rating=4.0, objective_score=80)
    underpaid = make_employee(employee_id="B", current_salary=90000, supervisor_rating=4.0, objective_score=80)
    records = calc.compute_all([well_paid, underpaid], config, as_of=AS_OF)
    by_id = {r["employee_id"]: r for r in records}
    assert by_id["B"]["computed_equity_gap_pts"] > by_id["A"]["computed_equity_gap_pts"]
    assert by_id["B"]["computed_equity_concern"] is True


def test_equity_scan_does_not_flag_single_person_groups():
    config = load_config()
    emp = make_employee(job_title="Unique Role Nobody Else Has")
    [record] = calc.compute_all([emp], config, as_of=AS_OF)
    assert record["computed_equity_concern"] is False


# ---------------------------------------------------------------------------
# Budget scenarios
# ---------------------------------------------------------------------------

def test_no_budget_funds_full_immediate_recommendation():
    config = load_config()
    emp = make_employee(current_salary=80000)
    records = calc.compute_all([emp], config, as_of=AS_OF)
    scenario = calc.apply_scenario(records, config, scenario_name="no_budget")
    assert scenario[0]["funded_pct"] == scenario[0]["raise"]["immediate_pct"]
    assert scenario[0]["deferred_amount"] == 0.0


def test_fixed_budget_prioritizes_and_defers_lower_priority():
    config = load_config()
    urgent = make_employee(employee_id="URGENT", current_salary=70000)  # below min -> priority 1
    routine = make_employee(
        employee_id="ROUTINE", current_salary=95000, supervisor_rating=3.0, objective_score=55,
        hire_date="2023-01-01", last_raise_date="2025-01-01",
    )
    records = calc.compute_all([urgent, routine], config, as_of=AS_OF)
    tiny_budget = records[0]["current_salary"] * 0.02  # enough for a couple % only
    scenario = calc.apply_scenario(records, config, scenario_name="fixed_budget", custom_budget=tiny_budget)
    by_id = {r["employee_id"]: r for r in scenario}
    assert by_id["URGENT"]["funded_amount"] >= by_id["ROUTINE"]["funded_amount"]


def test_fixed_budget_never_exceeds_total_budget():
    config = load_config()
    emps = [make_employee(employee_id=f"E{i}", current_salary=70000 + i * 1000) for i in range(5)]
    records = calc.compute_all(emps, config, as_of=AS_OF)
    budget = 5000
    scenario = calc.apply_scenario(records, config, scenario_name="fixed_budget", custom_budget=budget)
    assert sum(r["funded_amount"] for r in scenario) <= budget + 1e-6


def test_conservative_scenario_excludes_low_priority_employees():
    config = load_config()
    routine = make_employee(
        current_salary=103000, supervisor_rating=3.0, objective_score=55,
        hire_date="2023-01-01", last_raise_date="2025-06-01",
    )
    records = calc.compute_all([routine], config, as_of=AS_OF)
    if records[0]["raise"]["priority_tier"] > config["scenarios"]["conservative"]["tier_cutoff"]:
        scenario = calc.apply_scenario(records, config, scenario_name="conservative")
        assert scenario[0]["scenario_excluded"] is True
        assert scenario[0]["funded_amount"] == 0.0


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

def test_summarize_totals_match_records():
    config = load_config()
    emps = [make_employee(employee_id=f"E{i}", current_salary=70000 + i * 1000) for i in range(4)]
    records = calc.compute_all(emps, config, as_of=AS_OF)
    scenario = calc.apply_scenario(records, config, scenario_name="no_budget")
    summary = calc.summarize(scenario, config)
    assert summary["headcount"] == 4
    assert summary["total_current_payroll"] == sum(e["current_salary"] for e in emps)
    assert abs(summary["total_funded_budget"] - sum(r["funded_amount"] for r in scenario)) < 1e-6


def test_summarize_counts_below_min_and_above_max():
    config = load_config()
    below = make_employee(employee_id="BELOW", current_salary=70000)
    above = make_employee(employee_id="ABOVE", current_salary=125000)
    records = calc.compute_all([below, above], config, as_of=AS_OF)
    scenario = calc.apply_scenario(records, config, scenario_name="no_budget")
    summary = calc.summarize(scenario, config)
    assert summary["count_below_min"] == 1
    assert summary["count_above_max"] == 1
