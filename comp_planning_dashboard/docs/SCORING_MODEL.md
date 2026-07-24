# 3. Combined performance scoring & weighting model

## Why a blend, and why 50/50 by default

Supervisor ratings and objective performance metrics measure different
things and fail in different ways:

- **Supervisor ratings** capture context a dashboard can't (collaboration,
  judgment calls, ramping up in a hard quarter) but are vulnerable to recency
  bias, halo effects, and inconsistency between managers.
- **Objective metrics** (tickets closed, code shipped, quota attainment,
  uptime owned, etc.) are consistent and auditable but can miss context,
  reward volume over quality, or not exist yet for a newer role.

Neither should be trusted alone, which is why the spec asks for a *combined*
score with adjustable weights rather than picking one. **50/50 is the
starting assumption** here, not a researched optimum - it's a defensible,
easy-to-explain default until you have enough review cycles to see whether
one signal predicts retention/outcomes better than the other for your
org. Treat it as a hypothesis to revisit, not a settled answer.

**When to shift the weights:**
- Toward objective (e.g. 30/70): roles with mature, well-instrumented
  metrics where manager ratings have historically shown wide variance
  between teams for similar output.
- Toward supervisor (e.g. 70/30): roles where the "objective" metric is
  new, noisy, or easy to game, or where the work is inherently hard to
  quantify (e.g. early-stage product design).

Weights live in `config.json` → `performance.weight_supervisor` /
`weight_objective` and are editable live from the dashboard - they don't
have to sum to 1 (the formula normalizes by their sum), but keeping them
summing to 1 makes the resulting 0-100 scale easiest to reason about.

## Normalization

Supervisor ratings and objective scores rarely share a scale (1-5 vs.
0-100 is assumed here, both configurable via `supervisor_scale_max` /
`objective_scale_max`). Both are normalized to 0-100 before blending so the
weights mean what they say - a 0.5/0.5 blend of a 1-5 and a 0-100 score
without normalization would silently be dominated by whichever had the
bigger range.

## Performance tiers

The blended 0-100 score maps to five tiers, used throughout the rest of the
model (expected-position shifts, "high performer" checks, flight-risk
mismatch scoring):

| Tier | Floor |
|---|---|
| Top | 90 |
| High | 75 |
| Solid | 60 |
| Developing | 45 |
| Low | 0 |

These floors are illustrative and should be tuned to your actual score
distribution - if 80% of employees land in "Solid," the tiers aren't doing
their job of differentiating anyone.

## Divergence flagging

A ≥20-point gap (configurable) between the normalized supervisor rating and
normalized objective score sets `divergence_flag = True` with a direction
("Supervisor higher" / "Objective higher"). This is a **review prompt, not
an accusation** - it can mean the manager sees ramp-up/context the metric
doesn't capture, or it can mean the metric doesn't measure what matters for
that role, or it can mean an inflated/deflated rating. The dashboard shows
it as a flag on the row; deciding what it means is a human review step.

## What this model deliberately does NOT do

- It never overwrites or discards either input score - both stay visible in
  their own columns everywhere, per the "keep subjective and objective
  scores separate" governance requirement.
- It never treats the combined score as the *only* raise input - see
  RAISE_PRIORITIZATION.md for how position-in-range, tenure, criticality,
  flight risk, and equity all factor in independently.
- It does not attempt to correct for manager-to-manager rating bias
  (calibration). If that's a known problem in your org, it belongs upstream
  of this tool, in how supervisor ratings are calibrated before they're
  entered.
