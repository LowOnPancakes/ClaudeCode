# 10. Assumptions & limitations

## 10.1 Missing information that would materially change this design

These weren't available when this was built, so reasonable, clearly-labeled
assumptions were made instead. Before relying on this for a real compensation
cycle, get real answers to:

1. **Actual salary bands.** `data/salary_bands.csv` is an illustrative,
   general-knowledge set of SaaS/web-hosting pay ranges (US, remote-friendly,
   mid-market, single national band, base salary only) - **not** a licensed
   compensation survey (Radford, Pave, OpenComp, Option Impact/Shortlist,
   Carta Total Comp) and not any specific company's real bands. Replace this
   table before making real decisions from it.
2. **Geographic pay strategy.** Is pay single-national-band, geo-tiered, or
   fully localized? The current model has no location field or geo
   differential at all - every band is treated as one number regardless of
   where the employee sits.
3. **What's in "current salary."** Base only, as built. If your total-comp
   philosophy leans on bonus/commission/equity to manage retention (common
   in Sales, where OTE often matters more than base), those dollars are
   completely invisible to this model right now and would materially change
   both the raise math and the flight-risk read for those roles.
4. **How the "secondary objective performance dashboard" actually delivers
   data.** Built here as a plain CSV/manual-entry column. A real integration
   (API pull, scheduled export, whatever that system supports) needs its own
   design - refresh cadence, what happens to the combined score when it's
   stale, etc.
5. **Review cadence and history.** This model is a single point-in-time
   snapshot per employee (latest supervisor rating, latest objective score,
   most recent raise date). It does not store a multi-cycle history. If you
   need trend lines ("has this person's compa-ratio been declining for 3
   cycles"), that requires a `performance_history`/`comp_history` table (see
   DATA_STRUCTURE.md §1.5) this build doesn't include.
6. **Who's authorized to see this.** No authentication, no role-based access
   control, no audit log beyond the override history. This is a design gap
   requiring a decision (SSO? VPN-only? read-only view for managers vs.
   full access for HR/Comp?) before any real deployment - see §10.4.
7. **Promotion vs. raise.** A promotion (title/level/range change alongside
   the pay change) and a same-role raise are handled identically here - edit
   the employee's range fields and salary together. If your process
   distinguishes them (different approval chain, different budget category),
   that needs its own workflow this tool doesn't model.

## 10.2 Modeling assumptions (adjustable, but assumptions nonetheless)

- **50/50 performance blend** (SCORING_MODEL.md) - a defensible starting
  point, not a validated optimum for your organization.
- **Performance-tier floors** (90/75/60/45) and **expected-position-band
  shifts** (±12/±6/0 pts, tenure ±8/-3/0/+2, critical +4, band half-width
  7.5 pts) - illustrative HR-common heuristics, not derived from your actual
  pay/performance/attrition data.
- **Raise caps** (10% standard / 15% exception) and **exception conditions**
  - taken directly from the spec's own language, encoded as explicit rules.
- **Flight-risk weights and bands** - a reasonable starting composition
  (FLIGHT_RISK_MODEL.md), deliberately keeping "manual/subjective" inputs to
  a modest combined 20% of the score.
- **Internal-equity peer group** = same department + job title + level,
  minimum 2 people, ≥8-point compa-ratio gap. A small company will have many
  single-person "peer groups" where this check simply can't fire - that's
  expected, not a bug, but it does mean equity coverage is incomplete at low
  headcount.
- **Budget allocation** funds strictly by priority order (tier, then flight
  risk, then gap size) down to $0, with one partially-funded employee at the
  cutoff. It does not attempt any other allocation strategy (e.g., ensuring
  every department gets *something*, or smoothing so no one tier absorbs the
  entire cut) - if your budget conversations need that, the cutoff logic in
  `calc.py::apply_scenario` is the place to change it.
- **All dollar figures are nominal, single point-in-time.** No compounding
  math for phased plans beyond the two explicit phases; no inflation/COLA
  modeling; no modeling of payroll-tax/benefits load on top of the raise
  amount.

## 10.3 What this tool intentionally does not do (by design, per the governance ask)

- Does not use, request, or infer protected characteristics anywhere.
- Does not make a legal pay-equity determination - it only *surfaces* equity
  gaps (manual or computed) for a human review process.
- Does not let a performance score alone drive a raise - position-in-range,
  tenure, criticality, flight risk, and equity are independent contributing
  factors, not performance modifiers.
- Does not silently apply an HR override - every override requires a
  written justification and is stored next to (never over) the system's
  original recommendation.
- Does not silently drop incomplete records into the math - rows missing a
  required field (name/department/job title/salary/range) are excluded from
  calculations and listed explicitly in the Governance panel; rows missing
  an optional field (e.g. no `supervisor_rating` yet) are included but
  flagged as less reliable.

## 10.4 Before using this with real compensation data

- Put it behind your organization's normal auth (SSO/VPN/reverse proxy) -
  it ships with none.
- `data/state.json` is a plain, unencrypted local file once the app is
  running - fine for a demo, not fine for real PII/comp data at rest without
  changes (encryption at rest, a real database, backups, access logging).
- Review every default weight and threshold in `config.json` with your
  actual HR/Comp/Legal stakeholders before treating its output as more than
  a first-pass planning aid.
