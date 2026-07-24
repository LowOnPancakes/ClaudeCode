# 4. Raise-prioritization framework

## 4.1 Priority tiers

Every employee is evaluated against six urgency conditions, in this order
(an employee can match more than one; the **lowest-numbered match wins** as
their priority tier):

| Tier | Condition | Rationale |
|---|---|---|
| 1 | Current salary is below the range minimum | Often a legal/compliance floor, and the clearest, least-debatable case. |
| 2 | High/Top performer, significantly below their expected position band (gap ≥ `significant_gap_pts`, default 8 pts) | Rewards and retains the people whose loss hurts most, ahead of simply "who's lowest in range." |
| 3 | Flight-risk rating is High or Critical | Retention urgency, independent of *why* the risk is high. |
| 4 | Critical / difficult-to-replace role | Business-continuity risk, even absent an individual flight-risk signal. |
| 5 | Internal pay-equity concern (manual or computed peer-group gap) | Fairness risk that compounds the longer it's left unaddressed. |
| 6 | High/Top performer whose last raise was ≥ `long_cycle_months` (default 18) ago and who isn't already above the range max | Catches "quietly fell behind" cases that no single snapshot metric flags. |
| 7 | None of the above | Standard / monitor at the next normal review cycle. Still gets a calculated raise if their gap-to-expected-position is positive - priority governs *funding order under a budget*, not whether a number is calculated at all. |

This ordering is a judgment call, not a derived optimum - reorder it if your
organization weighs (say) role criticality above flight risk. It lives as
plain code in `calc.py::_matched_priority_reasons` if you need to change the
logic itself, or as thresholds in `config.json` if you just need to tune the
existing conditions.

## 4.2 Sizing the raise

1. **Target salary** = `band_center * range_mid` (see FORMULAS.md §2.3),
   raised further to the peer-group average if an equity concern applies, and
   to `range_min * 1.02` if the employee is below minimum.
2. **Full recommended gap %** = the % increase needed to reach that target
   (floored at 0 - nobody gets a negative "raise").
3. **Standard cap: 10%.** Applied whenever none of the exception conditions
   below are met.
4. **Exception cap: 15%**, only when at least one is true:
   - Below the range minimum.
   - A *severe* equity gap (≥ 2× the normal equity threshold, default 16 pts).
   - High/Top performer **and** High/Critical flight risk together.
   - Critical role **and** the gap exceeds 10%.
   - Market demand is "High" **and** the gap exceeds 10%.
   - Tier-6 (delayed adjustment) **and** the gap exceeds 10%.

   Every exception is recorded as plain-language reasons in
   `business_justification` - "an exception was applied because X" is never
   silent.
5. **Phasing.** If the full gap exceeds whatever cap applies, the recommendation
   splits: `immediate_pct` (this cycle, capped) + `phase2_pct` (next cycle, 6
   months out if an exception applied, 12 months otherwise, capped the same
   way). If a gap is so large that *two* capped phases still don't close it, the
   remainder is surfaced explicitly (`remaining_gap_after_phase2_pct`) with a
   note to schedule a third-phase review - the model never proposes exceeding
   15% in a single adjustment to avoid a third phase.

## 4.3 Budget scenarios

| Scenario | Behavior |
|---|---|
| **No fixed budget** | Every employee is funded at their full immediate (phase-1) recommendation. Nothing is deferred. |
| **Fixed budget** | You enter a dollar amount. Employees are funded **in priority order** (tier 1 first, then by flight-risk score, then by gap size) until the budget runs out; the employee at the cutoff gets a partial (pro-rated) amount, everyone after gets $0 and is marked deferred. This is the "prioritize without giving everyone the same %" requirement - nobody's raise is scaled down proportionally; funding order is by need, not evenly spread. |
| **Conservative** | Only tiers 1-2 are eligible at all; individual raises capped at 7%; effective pool sized off that eligible set. |
| **Moderate** | Tiers 1-4 eligible; individual raises capped at 12%. |
| **Aggressive market correction** | All tiers eligible; individual raises capped at 15% (the model's hard ceiling); effective pool scaled up (1.25×) to push further into closing gaps sooner. |

For every scenario the dashboard shows, per employee: the **full recommended
adjustment**, the **budget-constrained adjustment** actually being funded,
the **deferred amount** (the difference), and the **remaining compensation
gap** after the constrained raise is applied - so a budget decision never
quietly erases visibility into what was actually needed.

## 4.4 HR overrides

Any of the above can be overridden from the dashboard. An override:

- Requires a written justification (enforced - the form rejects a blank one).
- Is stored as a new entry in the append-only override log, never edited in
  place, alongside the system's original recommendation.
- Is clearly labeled in the table ("HR override, was X%") so a viewer never
  mistakes an override for the model's own recommendation.
