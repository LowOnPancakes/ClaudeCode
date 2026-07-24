# 2. Formulas & calculation logic

All of this is implemented in `calc.py` as small, independently unit-tested
functions (`tests/test_calc.py`). This document mirrors the code so the two
never drift silently - if you change a formula, update both.

## 2.1 Salary position in range

```
salary_position_pct = (current_salary - range_min) / (range_max - range_min)
```

Displayed as a percentage. 0% = at the range minimum, 100% = at the range
maximum; it can go below 0% or above 100% when the salary itself is outside
the range (see §2.3).

## 2.2 Compa-ratio

```
compa_ratio = current_salary / range_mid
```

Displayed both as a decimal (e.g. `0.94`) and a percentage (`94%`).

## 2.3 Expected position band (not "everyone belongs at the midpoint")

The spec explicitly says not to assume a flat midpoint target. Instead,
every employee gets an **expected compa-ratio band**, centered on a value
that shifts based on performance, tenure, and role criticality:

```
performance_shift = performance_shift_pts[combined_performance_tier] / 100
tenure_shift       = tenure_shift_pts[bucket(tenure_years)] / 100
critical_shift     = critical_role_shift_pts / 100   (else 0)

band_center = 1.00 + performance_shift + tenure_shift + critical_shift
band_low    = band_center - band_half_width_pts / 100
band_high   = band_center + band_half_width_pts / 100
```

Default shifts (`data/config.json` → `position_model`):

| Performance tier | Shift (pts) | | Tenure | Shift (pts) |
|---|---|---|---|---|
| Top | +12 | | < 1 yr (still ramping) | -8 |
| High | +6 | | 1-2 yr | -3 |
| Solid | 0 | | 2-5 yr | 0 |
| Developing | -6 | | 5 yr + | +2 |
| Low | -12 | | | |

Critical role: +4 pts. Band half-width: 7.5 pts (i.e. ±7.5% around center).
All of these are adjustable from the dashboard's Weights panel or directly
in `config.json`.

## 2.4 Salary position category

```
if current_salary < range_min:      "Below Minimum"
elif current_salary > range_max:    "Above Maximum"
elif compa_ratio < band_low:        "Low in Range"
elif compa_ratio > band_high:       "High in Range"
else:                                "Appropriately Positioned"
```

Because `band_low`/`band_high` are per-employee (from §2.3), two employees
at the exact same compa-ratio can land in different categories - e.g. a Top
performer at 100% of midpoint reads as "Low in Range" (their band starts
above 100%), while a Developing performer at 100% reads as "High in Range."

## 2.5 Combined performance score

```
supervisor_normalized = supervisor_rating / supervisor_scale_max * 100      (default scale max 5)
objective_normalized  = objective_score / objective_scale_max * 100         (default scale max 100)

combined_score = (supervisor_normalized * weight_supervisor
                 + objective_normalized  * weight_objective)
                 / (weight_supervisor + weight_objective)
```

Default weights are 50/50 - see SCORING_MODEL.md for the rationale and how
to change them. The two normalized scores are never discarded: they stay in
their own columns everywhere (table, export, detail view) alongside the
blended score.

**Divergence flag:**

```
divergence_points = |supervisor_normalized - objective_normalized|
divergence_flag = divergence_points >= divergence_flag_points   (default 20)
direction = "Supervisor higher" if supervisor_normalized > objective_normalized
            else "Objective higher"
```

## 2.6 Internal-equity peer scan

A computed check that runs *alongside* the manual `internal_equity_flag`,
grouping employees by `(department, job_title, level)` (level is included so
a Level I and a Level III are never compared as pay peers):

```
peer_group_avg_compa = mean(compa_ratio for employees in the same group)
equity_gap_pts = (peer_group_avg_compa - employee.compa_ratio) * 100
computed_equity_concern = equity_gap_pts >= gap_threshold_pts (default 8)
                           AND employee.performance_tier not in (Developing, Low)
```

Groups smaller than `min_group_size` (default 2) are skipped - there's no
"peer average" with a group of one. A Developing/Low performer paid below
the group average is not flagged; that's an expected, performance-linked
gap, not an equity concern.

`equity_concern = internal_equity_flag (manual) OR computed_equity_concern`.

## 2.7 Flight-risk score

See FLIGHT_RISK_MODEL.md for the full weighting rationale. Each factor
produces a 0-100 sub-score; the overall score is their weighted average,
mapped to a Low/Moderate/High/Critical band.

## 2.8 Raise recommendation

See RAISE_PRIORITIZATION.md for the full priority + sizing model. In brief:

```
target_salary = band_center * range_mid
                (raised to at least peer_group_avg_compa * range_mid if an equity concern applies,
                 and to at least range_min * 1.02 if below minimum)

gap_pct = max(0, (target_salary - current_salary) / current_salary * 100)

cap = exception_cap_pct (15) if any exception condition is met, else standard_cap_pct (10)
immediate_pct = min(gap_pct, cap)
phase2_pct    = min(gap_pct - immediate_pct, cap)   (only if gap_pct > cap)
```

## 2.9 Post-raise recalculation

Every "new" column in the output table (new compa-ratio, new salary
position, new position category) is the §2.1-§2.4 formulas re-applied to
`current_salary + funded_amount` - not a separate estimate.

## 2.10 Summary aggregations

- **Total current payroll** = Σ `current_salary`
- **Total recommended raise budget** = Σ `funded_amount` (i.e. what the *current scenario* actually funds - see SCENARIOS in RAISE_PRIORITIZATION.md)
- **Overall payroll increase %** = total funded budget / total current payroll
- **Below-min / above-max counts** = counts of the §2.4 categories
- **Compa-ratio-below-threshold count** = count where `compa_ratio < compa_ratio_low_threshold` (default 0.90)
- **High/Critical flight-risk count** = count where flight-risk rating is High or Critical
- **By department / performance tier / priority** = the same funded-amount sum, grouped
- **Immediate vs. phased cost** = funded amount split by whether that employee's plan is phased
- **Before/after compa-ratio and position distributions** = histogram bucket counts, computed once on `current_salary` and once on `current_salary + funded_amount`
