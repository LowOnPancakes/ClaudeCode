# 1. Data structure

The tool uses four source tables. In this reference implementation they are
plain CSV/JSON files under `data/`; in a production deployment they would
more naturally live in a small relational schema (shown at the bottom of
this document), but the columns and relationships are the same either way.

## 1.1 `employees` (`data/employees_sample.csv`)

One row per employee, per review cycle. This is the primary "employee-level
inputs" table requested in the spec.

| Column | Type | Notes |
|---|---|---|
| `employee_id` | string (PK) | Stable identifier - never reused. |
| `name` | string | Display name. Use an ID-only view if you need to mask names during calibration. |
| `department` | string | Team/department. |
| `job_title` | string | Must match a row in `salary_bands` for the auto-fill lookup to work, but the range fields below are what the engine actually uses - job title/level are descriptive. |
| `level` | string | e.g. "I", "Senior", "Manager". Also part of the internal-equity peer-group key (see FORMULAS.md §7). |
| `hire_date` | date (`YYYY-MM-DD`) | Used for tenure and, when `last_raise_date` is blank, as the anchor for "time since last raise." |
| `current_salary` | number | Base salary only. Commissions/OTE/equity are out of scope - see ASSUMPTIONS.md. |
| `range_min` / `range_mid` / `range_max` | number | The employee's applicable salary range. Can be auto-filled from `salary_bands` or entered directly, and can differ from the reference table (e.g. a negotiated exception). |
| `supervisor_rating` | number (1-5) | Subjective manager input. Kept in its own column everywhere - never overwritten by the objective score. |
| `objective_score` | number (0-100) | Imported from the secondary objective-metrics dashboard. Also kept in its own column throughout. |
| `last_raise_date` | date, optional | Blank = never raised since hire. |
| `critical_role` | `Y`/`N` | Business-critical / difficult-to-replace flag. |
| `market_demand` | `Low`/`Medium`/`High` | Manual, subjective input on external market heat for this person's skill set. |
| `internal_equity_flag` | `Y`/`N` | Manual HR flag. Combined with a *computed* peer-comparison flag (FORMULAS.md §7) - either one sets `equity_concern`. |
| `retention_notes` | free text | Manual, subjective. Presence of text is itself treated as a signal (see FLIGHT_RISK_MODEL.md) - keep it factual, not speculative. |

Tenure and role-criticality are both marked optional in the original ask;
if `hire_date` is blank, tenure-based adjustments and time-since-raise
default to a neutral value and the record is flagged under "data quality"
rather than guessed at.

## 1.2 `salary_bands` (`data/salary_bands.csv`)

The market-reference table: SaaS/web-hosting pay ranges by department, job
title, and level. See ASSUMPTIONS.md for sourcing caveats - these are
illustrative starting bands, not a licensed survey.

| Column | Notes |
|---|---|
| `department`, `job_title`, `level` | Lookup key. |
| `range_min`, `range_mid`, `range_max` | Same semantics as on `employees`. |
| `notes` | e.g. "hot external market," "24/7 shift coverage." |

## 1.3 `config` (`data/config.json`)

Every adjustable weight/threshold in the model: performance-blend weights,
divergence-flag threshold, expected-position-band shifts, raise caps, the
internal-equity gap threshold, flight-risk factor weights and bands, compa-
ratio thresholds, and the budget-scenario presets. See FORMULAS.md,
SCORING_MODEL.md, RAISE_PRIORITIZATION.md and FLIGHT_RISK_MODEL.md for what
each value drives. Runtime tweaks made from the dashboard's "Weights &
thresholds" panel are layered on top of this file (see `state.json` below)
rather than overwriting it, so the checked-in defaults stay a clean
reference.

## 1.4 Working state (`data/state.json`, generated - not checked in)

Holds everything that changes between dashboard sessions:

- `employees` - the live working copy (seeded from `employees_sample.csv`, then edited/added-to from the dashboard).
- `overrides` - append-only log: `{employee_id, override_pct, justification, approver, timestamp}`. The latest entry per employee wins; history is preserved for audit.
- `config_overrides` - a partial config tree deep-merged over `config.json` at read time.
- `scenario` - the currently selected budget scenario (`{name, budget}`).

## 1.5 Equivalent relational schema

If you outgrow flat files:

```sql
CREATE TABLE employees (
  employee_id TEXT PRIMARY KEY,
  name TEXT, department TEXT, job_title TEXT, level TEXT,
  hire_date DATE, current_salary NUMERIC,
  range_min NUMERIC, range_mid NUMERIC, range_max NUMERIC,
  supervisor_rating NUMERIC, objective_score NUMERIC,
  last_raise_date DATE, critical_role BOOLEAN,
  market_demand TEXT, internal_equity_flag BOOLEAN, retention_notes TEXT
);

CREATE TABLE salary_bands (
  department TEXT, job_title TEXT, level TEXT,
  range_min NUMERIC, range_mid NUMERIC, range_max NUMERIC, notes TEXT,
  PRIMARY KEY (department, job_title, level)
);

CREATE TABLE overrides (
  id SERIAL PRIMARY KEY, employee_id TEXT REFERENCES employees(employee_id),
  override_pct NUMERIC, justification TEXT, approver TEXT, created_at TIMESTAMP
);

CREATE TABLE config_settings (
  key TEXT PRIMARY KEY, value JSONB
);
```

`performance_scores` is deliberately *not* a separate history table in this
reference build - only the latest supervisor rating and objective score are
kept per employee. A production version tracking multiple review cycles
should split those into a `performance_history(employee_id, cycle, supervisor_rating,
objective_score, recorded_at)` table and have the dashboard read the latest
row per employee, which changes none of the formulas below.
