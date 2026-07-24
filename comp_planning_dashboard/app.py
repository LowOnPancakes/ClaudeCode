"""Flask app for the compensation planning dashboard.

This is intentionally a server-rendered app (no JS build step, no database) -
same philosophy as the org_chart_converter tool elsewhere in this repo. All
calculation logic lives in calc.py; this file only loads data, calls it, and
renders/accepts forms.
"""

from __future__ import annotations

import csv
import datetime
import io
import json

from flask import Flask, render_template, request, redirect, url_for, Response

import calc
import data_store

app = Flask(__name__)


@app.template_filter("money")
def money_filter(value):
    if value is None:
        return "—"
    return "${:,.0f}".format(value)


@app.template_filter("pct")
def pct_filter(value, decimals=1):
    if value is None:
        return "—"
    return "{:.{d}f}%".format(value, d=decimals)


@app.template_filter("ratio_pct")
def ratio_pct_filter(value, decimals=1):
    if value is None:
        return "—"
    return "{:.{d}f}%".format(value * 100, d=decimals)


@app.template_filter("num")
def num_filter(value, decimals=1):
    if value is None:
        return "—"
    return "{:.{d}f}".format(value, d=decimals)


@app.template_filter("slug")
def slug_filter(value):
    return str(value).lower().replace(" ", "-")


PERFORMANCE_TIER_ORDER = ["Top", "High", "Solid", "Developing", "Low"]
COMPA_BUCKET_ORDER = ["<85%", "85-95%", "95-105%", "105-115%", "115%+", "Unknown"]
POSITION_CATEGORY_ORDER = [
    "Below Minimum", "Low in Range", "Appropriately Positioned", "High in Range", "Above Maximum",
]
FLIGHT_RISK_ORDER = ["Low", "Moderate", "High", "Critical"]


def build_chart_data(summary):
    dept_items = sorted(summary["by_department"].items(), key=lambda kv: -kv[1]["funded_amount"])
    dept_budget = {
        "labels": [k for k, _ in dept_items],
        "values": [round(v["funded_amount"], 2) for _, v in dept_items],
    }

    perf_budget = {
        "labels": [t for t in PERFORMANCE_TIER_ORDER if t in summary["by_performance_tier"]],
        "values": [
            round(summary["by_performance_tier"][t]["funded_amount"], 2)
            for t in PERFORMANCE_TIER_ORDER if t in summary["by_performance_tier"]
        ],
    }

    priority_items = sorted(summary["by_priority"].items(), key=lambda kv: kv[0])
    priority_budget = {
        "labels": [f"P{k}: {v['label']}" for k, v in priority_items],
        "values": [round(v["funded_amount"], 2) for _, v in priority_items],
    }

    immediate_vs_phased = {
        "labels": ["Immediate", "Phased (year-1 tranche)"],
        "values": [round(summary["immediate_cost"], 2), round(summary["phased_cost"], 2)],
    }

    compa_dist = {
        "labels": [b for b in COMPA_BUCKET_ORDER if b in summary["before_compa_distribution"] or b in summary["after_compa_distribution"]],
    }
    compa_dist["before"] = [summary["before_compa_distribution"].get(b, 0) for b in compa_dist["labels"]]
    compa_dist["after"] = [summary["after_compa_distribution"].get(b, 0) for b in compa_dist["labels"]]

    position_dist = {"labels": POSITION_CATEGORY_ORDER}
    position_dist["before"] = [summary["before_position_distribution"].get(c, 0) for c in POSITION_CATEGORY_ORDER]
    position_dist["after"] = [summary["after_position_distribution"].get(c, 0) for c in POSITION_CATEGORY_ORDER]

    return {
        "dept_budget": dept_budget,
        "perf_budget": perf_budget,
        "priority_budget": priority_budget,
        "immediate_vs_phased": immediate_vs_phased,
        "compa_dist": compa_dist,
        "position_dist": position_dist,
    }


def flight_risk_counts(records):
    counts = {r: 0 for r in FLIGHT_RISK_ORDER}
    for rec in records:
        counts[rec["flight_risk"]["rating"]] += 1
    return {"labels": FLIGHT_RISK_ORDER, "values": [counts[r] for r in FLIGHT_RISK_ORDER]}

FLOAT_FIELDS = [
    "current_salary", "range_min", "range_mid", "range_max",
    "supervisor_rating", "objective_score",
]


def to_float(value, default=None):
    try:
        if value in (None, ""):
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def parse_employee_form(form):
    fields = {
        "employee_id": form.get("employee_id", "").strip(),
        "name": form.get("name", "").strip(),
        "department": form.get("department", "").strip(),
        "job_title": form.get("job_title", "").strip(),
        "level": form.get("level", "").strip(),
        "hire_date": form.get("hire_date", "").strip() or None,
        "last_raise_date": form.get("last_raise_date", "").strip() or None,
        "critical_role": "Y" if form.get("critical_role") == "on" else "N",
        "internal_equity_flag": "Y" if form.get("internal_equity_flag") == "on" else "N",
        "market_demand": form.get("market_demand", "Low"),
        "retention_notes": form.get("retention_notes", "").strip(),
    }
    for f in FLOAT_FIELDS:
        raw = form.get(f, "").strip()
        fields[f] = raw if raw != "" else None
    return fields


def parse_weight_overrides(form):
    """Builds a nested config_overrides dict from whatever weight/threshold
    inputs were submitted on the Weights & Scenarios panel."""
    overrides = {}

    def set_path(path, value):
        node = overrides
        parts = path.split(".")
        for p in parts[:-1]:
            node = node.setdefault(p, {})
        node[parts[-1]] = value

    simple_float_paths = [
        "performance.weight_supervisor",
        "performance.weight_objective",
        "performance.divergence_flag_points",
        "position_model.band_half_width_pts",
        "raise_model.standard_cap_pct",
        "raise_model.exception_cap_pct",
        "raise_model.significant_gap_pts",
        "raise_model.long_cycle_months",
        "compa_ratio_low_threshold",
        "compa_ratio_high_threshold",
        "flight_risk.weights.comp_position",
        "flight_risk.weights.compa_ratio_gap",
        "flight_risk.weights.time_since_raise",
        "flight_risk.weights.performance_pay_mismatch",
        "flight_risk.weights.tenure_curve",
        "flight_risk.weights.market_demand",
        "flight_risk.weights.retention_notes",
    ]
    for path in simple_float_paths:
        raw = form.get(path)
        val = to_float(raw)
        if val is not None:
            set_path(path, val)
    return overrides


def split_valid_and_incomplete(raw_employees):
    valid, incomplete = [], []
    for e in raw_employees:
        missing = data_store.record_missing_fields(e)
        if missing:
            incomplete.append({"employee": e, "missing_fields": missing})
        else:
            valid.append(e)
    return valid, incomplete


def apply_overrides(records, overrides_by_emp):
    for r in records:
        ov = overrides_by_emp.get(r["employee_id"])
        r["override"] = ov
        r["system_funded_pct"] = r["funded_pct"]
        r["system_funded_amount"] = r["funded_amount"]
        if ov and ov.get("override_pct") is not None:
            r["funded_pct"] = round(float(ov["override_pct"]), 2)
            r["funded_amount"] = round(r["current_salary"] * r["funded_pct"] / 100.0, 2)
    calc.finalize_scenario_fields(records)
    return records


def build_dashboard_context(error=None, notice=None):
    state = data_store.load_state()
    config = data_store.effective_config(state)
    base_config = data_store.load_base_config()
    bands = data_store.load_salary_bands()
    as_of = datetime.date.today()

    valid_raw, incomplete = split_valid_and_incomplete(state["employees"])

    records = calc.compute_all(valid_raw, config, as_of=as_of)

    scenario = state.get("scenario", {"name": "no_budget", "budget": None})
    records = calc.apply_scenario(
        records, config,
        scenario_name=scenario.get("name", "no_budget"),
        custom_budget=scenario.get("budget"),
    )

    overrides_by_emp = data_store.latest_overrides_by_employee(state)
    apply_overrides(records, overrides_by_emp)

    summary = calc.summarize(records, config)
    records.sort(key=lambda r: (r["raise"]["priority_tier"], r["department"], r["name"]))

    departments = sorted({r["department"] for r in records})

    chart_data = build_chart_data(summary)
    chart_data["flight_risk_counts"] = flight_risk_counts(records)

    return {
        "records": records,
        "summary": summary,
        "config": config,
        "base_config": base_config,
        "bands": bands,
        "scenario": scenario,
        "departments": departments,
        "incomplete": incomplete,
        "as_of": as_of.isoformat(),
        "error": error,
        "notice": notice,
        "priority_labels": calc.PRIORITY_LABELS,
        "chart_data_json": json.dumps(chart_data),
    }


@app.route("/")
def dashboard():
    ctx = build_dashboard_context(
        error=request.args.get("error"),
        notice=request.args.get("notice"),
    )
    return render_template("index.html", **ctx)


@app.route("/scenario", methods=["POST"])
def update_scenario():
    state = data_store.load_state()
    name = request.form.get("scenario_name", "no_budget")
    budget = to_float(request.form.get("budget_amount"))
    state["scenario"] = {"name": name, "budget": budget if name == "fixed_budget" else None}
    data_store.save_state(state)
    return redirect(url_for("dashboard", notice="Scenario updated."))


@app.route("/weights", methods=["POST"])
def update_weights():
    state = data_store.load_state()
    state["config_overrides"] = parse_weight_overrides(request.form)
    data_store.save_state(state)
    return redirect(url_for("dashboard", notice="Weights and thresholds updated."))


@app.route("/weights/reset", methods=["POST"])
def reset_weights():
    state = data_store.load_state()
    state["config_overrides"] = {}
    data_store.save_state(state)
    return redirect(url_for("dashboard", notice="Weights reset to defaults."))


@app.route("/employee", methods=["POST"])
def upsert_employee():
    fields = parse_employee_form(request.form)
    if not fields["name"] or not fields["department"] or not fields["job_title"]:
        return redirect(url_for("dashboard", error="Name, department, and job title are required."))
    if fields["current_salary"] is None or fields["range_min"] is None or fields["range_mid"] is None or fields["range_max"] is None:
        return redirect(url_for("dashboard", error="Current salary and the full salary range are required."))

    state = data_store.load_state()
    data_store.upsert_employee(state, fields)
    data_store.save_state(state)
    return redirect(url_for("dashboard", notice=f"Saved {fields['name']}."))


@app.route("/employee/<employee_id>/delete", methods=["POST"])
def delete_employee(employee_id):
    state = data_store.load_state()
    data_store.delete_employee(state, employee_id)
    data_store.save_state(state)
    return redirect(url_for("dashboard", notice="Employee removed."))


@app.route("/override", methods=["POST"])
def submit_override():
    employee_id = request.form.get("employee_id", "").strip()
    override_pct = to_float(request.form.get("override_pct"))
    justification = request.form.get("justification", "")
    approver = request.form.get("approver", "")

    state = data_store.load_state()
    try:
        data_store.add_override(state, employee_id, override_pct, justification, approver)
    except ValueError as exc:
        return redirect(url_for("dashboard", error=str(exc)))
    data_store.save_state(state)
    return redirect(url_for("dashboard", notice="Override recorded."))


@app.route("/reset-demo-data", methods=["POST"])
def reset_demo_data():
    data_store.reset_state()
    return redirect(url_for("dashboard", notice="Demo data reset to the original sample set."))


EXPORT_COLUMNS = [
    ("employee_id", "Employee ID"),
    ("name", "Employee"),
    ("department", "Department"),
    ("job_title", "Role"),
    ("current_salary", "Current Salary"),
    ("range_min", "Range Min"),
    ("range_mid", "Range Mid"),
    ("range_max", "Range Max"),
    ("position_pct", "Salary Position %"),
    ("compa_ratio", "Compa-Ratio"),
    ("position_category", "Position Category"),
    ("supervisor_rating", "Supervisor Rating"),
    ("objective_score", "Objective Score"),
    ("__combined_score", "Combined Performance Score"),
    ("__flight_risk_rating", "Flight-Risk Rating"),
    ("__final_pct", "Recommended Raise %"),
    ("funded_amount", "Recommended Raise $"),
    ("scenario_new_salary", "Proposed New Salary"),
    ("scenario_new_compa_ratio", "New Compa-Ratio"),
    ("scenario_new_position_pct", "New Salary Position %"),
    ("__priority_label", "Priority Level"),
    ("__adjustment_timing", "Immediate or Phased"),
    ("__business_justification", "Business Justification"),
    ("__requires_review", "Requires Review"),
]


@app.route("/export.csv")
def export_csv():
    ctx = build_dashboard_context()
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow([label for _, label in EXPORT_COLUMNS])
    for r in ctx["records"]:
        row = {
            "__combined_score": round(r["performance"]["combined_score"], 1) if r["performance"]["combined_score"] is not None else "",
            "__flight_risk_rating": r["flight_risk"]["rating"],
            "__final_pct": r["funded_pct"],
            "__priority_label": r["raise"]["priority_label"],
            "__adjustment_timing": r["raise"]["adjustment_timing"],
            "__business_justification": r["raise"]["business_justification"],
            "__requires_review": "Yes" if r["raise"]["requires_review"] else "No",
        }
        row.update(r)
        writer.writerow([row.get(key, "") for key, _ in EXPORT_COLUMNS])
    return Response(
        buf.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=compensation_plan_export.csv"},
    )


if __name__ == "__main__":
    app.run(debug=True, port=5000)
