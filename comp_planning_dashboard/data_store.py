"""Loads reference data (pay bands, config) and manages the working copy of
employee data + HR overrides.

Design: the checked-in CSV/JSON files under data/ are the *seed*. All runtime
edits (new employees, field edits, scenario choice, weight tweaks, HR
overrides) are written to data/state.json, so the seed files always stay a
clean example you can diff against or reset to.
"""

from __future__ import annotations

import copy
import csv
import json
import os
import threading

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
CONFIG_PATH = os.path.join(DATA_DIR, "config.json")
SALARY_BANDS_PATH = os.path.join(DATA_DIR, "salary_bands.csv")
EMPLOYEES_SEED_PATH = os.path.join(DATA_DIR, "employees_sample.csv")
STATE_PATH = os.path.join(DATA_DIR, "state.json")

_lock = threading.Lock()

REQUIRED_FIELDS = [
    "employee_id", "name", "department", "job_title", "current_salary",
    "range_min", "range_mid", "range_max",
]


def load_base_config():
    with open(CONFIG_PATH) as f:
        return json.load(f)


def load_salary_bands():
    with open(SALARY_BANDS_PATH) as f:
        return list(csv.DictReader(f))


def _load_seed_employees():
    with open(EMPLOYEES_SEED_PATH) as f:
        return list(csv.DictReader(f))


def _default_state():
    return {
        "employees": _load_seed_employees(),
        "overrides": [],
        "config_overrides": {},
        "scenario": {"name": "no_budget", "budget": None},
        "next_employee_seq": 31,
    }


def load_state():
    with _lock:
        if not os.path.exists(STATE_PATH):
            state = _default_state()
            _write_state(state)
            return state
        with open(STATE_PATH) as f:
            return json.load(f)


def _write_state(state):
    with open(STATE_PATH, "w") as f:
        json.dump(state, f, indent=2, default=str)


def save_state(state):
    with _lock:
        _write_state(state)


def reset_state():
    with _lock:
        state = _default_state()
        _write_state(state)
        return state


def _deep_merge(base, overrides):
    result = copy.deepcopy(base)
    for key, value in overrides.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def effective_config(state):
    return _deep_merge(load_base_config(), state.get("config_overrides", {}))


def find_employee(state, employee_id):
    for e in state["employees"]:
        if e["employee_id"] == employee_id:
            return e
    return None


def next_employee_id(state):
    seq = state.get("next_employee_seq", len(state["employees"]) + 1)
    state["next_employee_seq"] = seq + 1
    return f"E{seq:03d}"


def upsert_employee(state, fields):
    """Adds a new employee, or updates an existing one if employee_id matches."""
    employee_id = (fields.get("employee_id") or "").strip()
    existing = find_employee(state, employee_id) if employee_id else None
    if existing:
        existing.update({k: v for k, v in fields.items() if v is not None})
        return existing
    if not employee_id:
        employee_id = next_employee_id(state)
    fields["employee_id"] = employee_id
    state["employees"].append(fields)
    return fields


def delete_employee(state, employee_id):
    state["employees"] = [e for e in state["employees"] if e["employee_id"] != employee_id]


def latest_overrides_by_employee(state):
    latest = {}
    for entry in state.get("overrides", []):
        latest[entry["employee_id"]] = entry
    return latest


def add_override(state, employee_id, override_pct, justification, approver):
    if not justification or not justification.strip():
        raise ValueError("A written justification is required for every HR override.")
    import datetime
    entry = {
        "employee_id": employee_id,
        "override_pct": override_pct,
        "justification": justification.strip(),
        "approver": (approver or "").strip() or "Unspecified",
        "timestamp": datetime.date.today().isoformat(),
    }
    state.setdefault("overrides", []).append(entry)
    return entry


def record_missing_fields(raw_employee):
    """Surface incomplete/unreliable rows for the governance panel rather than
    silently guessing at values."""
    missing = [f for f in REQUIRED_FIELDS if not str(raw_employee.get(f, "")).strip()]
    return missing


def lookup_band(bands, department, job_title, level=None):
    for b in bands:
        if b["department"] == department and b["job_title"] == job_title:
            if level is None or b["level"] == level:
                return b
    return None
