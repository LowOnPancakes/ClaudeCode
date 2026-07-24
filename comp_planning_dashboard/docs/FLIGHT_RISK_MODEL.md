# 5. Flight-risk scoring framework

## 5.1 Design goal

The spec is explicit: **separate what is measured from what is judgment**,
and never present flight risk as a certainty. This model does both by
computing every factor as its own labeled 0-100 sub-score, then reporting
three numbers per employee instead of one:

- **Measurable score** - built only from compensation and tenure data already
  in the system (nothing here requires a human to have typed an opinion).
- **Subjective score** - built only from two manually-entered fields
  (`market_demand`, `retention_notes`).
- **Overall score / rating** - the full weighted blend, which is what
  drives the Low/Moderate/High/Critical rating and feeds raise
  prioritization (tier 3).

The dashboard always shows measurable and subjective side by side
(`meas. NN / subj. NN`) next to the overall rating, so nobody mistakes a
manager's hunch for a data-backed number, or vice versa.

## 5.2 Factors and default weights

| Factor | Weight | Type | Scoring logic |
|---|---|---|---|
| Salary position in range | 0.28 | Measurable | Below Minimum=100, Low in Range=65, Appropriate=25, High in Range=10, Above Maximum=5 |
| Compa-ratio gap vs. expected band | 0.12 | Measurable | 0 if at/above the expected band; scales up to 100 the further below it the employee sits |
| Time since last raise | 0.15 | Measurable | Bucketed: ≤12mo=10, ≤18mo=30, ≤24mo=55, ≤36mo=75, 36mo+=95 |
| High performer / low pay mismatch | 0.15 | Measurable | 90 if a High/Top performer is Below Minimum or Low in Range; 30 if High/Top but only borderline; 10 otherwise |
| Tenure curve | 0.10 | Measurable | <1yr=25 (still deciding if the job's a fit), 1-3yr=55 (classic post-onboarding risk window), 3-7yr=35, 7yr+=20 |
| Market demand for skills | 0.10 | **Subjective (manual)** | Low=15, Medium=45, High=80 |
| Retention notes present | 0.10 | **Subjective (manual)** | 70 if any text is entered, 15 if blank |

Weights sum to 1.0 by default and are independently adjustable from the
dashboard's "Flight-risk factor weights" panel.

## 5.3 Rating bands

```
score <= 30  -> Low
score <= 55  -> Moderate
score <= 78  -> High
score  > 78  -> Critical
```

## 5.4 Why these particular factors

- **Position/compa-ratio gap** and **mismatch** operationalize the core
  intuition that being paid below where your performance and tenure say you
  should be is itself a retention risk - not just "low pay" in the
  abstract.
- **Time since last raise** captures stagnation even when current pay looks
  fine on paper (an employee who hasn't been touched in 3 years is a
  different risk profile than one who was just adjusted, even at an
  identical compa-ratio today).
- **Tenure curve** encodes a common HR heuristic: brand-new hires are
  usually not yet flight risks (they just accepted an offer), but the
  1-3 year window - past onboarding, before deep loyalty/vesting/identity
  with the company - is where voluntary attrition risk typically peaks.
  This is a generalization, not a fact about any individual; treat it as a
  weak prior, not a prediction.
- **Market demand** and **retention notes** are kept in the model because
  ignoring known signal (a recruiter call, a hot skill set) would make the
  score less useful - but they're weighted modestly (0.10 each) and always
  shown separately so they can't silently dominate an otherwise-fine
  compensation picture, or be mistaken for something the system "detected."

## 5.5 What this does NOT do

- It does not predict whether any individual will actually leave. "Critical"
  means several risk factors point the same direction, not a probability.
- It does not use protected characteristics, and nothing about `retention_notes`
  should reference them - the field is for factual retention-relevant
  events (a recruiter contact, a stated intent to leave), not speculation
  about someone's personal circumstances.
- Role criticality is intentionally **not** a flight-risk factor here - it's
  treated as an organizational-impact multiplier (priority tier 4, see
  RAISE_PRIORITIZATION.md), not evidence that the person themselves is more
  or less likely to leave.
