# Compensation Planning Dashboard

An internal tool for planning a compensation review cycle at a SaaS /
web-hosting company: enter employee-level pay and performance data, see
where each person sits in their salary range, flag retention risk, and get
a prioritized, budget-aware raise recommendation - with HR override and
governance guardrails built in.

This is a server-rendered Flask app (no build step, no JS framework, no
database) - same philosophy as `org_chart_converter/` elsewhere in this
repo. All the math lives in `calc.py`, independently unit-tested, so the
model can be audited and changed without touching the web layer.

## What's here

```
comp_planning_dashboard/
  app.py                  Flask routes - loads data, calls calc.py, renders/accepts forms
  calc.py                 All formulas, scoring, prioritization, flight-risk, budget logic
  data_store.py           Loads config/CSV seeds, manages runtime state + overrides
  data/
    config.json           Every adjustable weight/threshold (documented + editable in-app)
    salary_bands.csv       Illustrative SaaS/web-hosting pay ranges by role/level
    employees_sample.csv   30 sample employees covering every scenario the model handles
  templates/index.html    The dashboard
  static/style.css, dashboard.js
  tests/test_calc.py      26 unit tests covering the formulas and edge cases
  docs/                   Deliverables 1-7 & 10 (see below)
```

## Quick start

```bash
cd comp_planning_dashboard
pip install -r requirements.txt
python app.py
```

Open `http://localhost:5000`. The first run seeds `data/state.json` from
`data/employees_sample.csv` - edit, add employees, change scenarios, adjust
weights, and record overrides from the browser; nothing you do touches the
checked-in sample files. Use the "Reset demo data" button (or delete
`data/state.json`) to start over.

Run the tests:

```bash
pip install pytest
pytest tests/
```

## Running it for real use

```bash
pip install gunicorn
gunicorn -w 2 -b 0.0.0.0:8000 app:app
```

- **Docker**: `docker build -t comp-planning-dashboard . && docker run -p 8000:8000 -v $(pwd)/data:/app/data comp-planning-dashboard` (the volume mount keeps `state.json` - i.e. your live edits and overrides - across container restarts).
- **cPanel (Phusion Passenger)**: same pattern as `org_chart_converter/webapp` - upload this folder's contents, set the application startup file to `passenger_wsgi.py` and entry point to `application`, then `pip install -r requirements.txt` in the app's virtualenv and restart. See that folder's README for the click-by-click cPanel steps; they transfer directly.

This handles real compensation data once you point it at a real roster -
**put it behind your normal auth (SSO/VPN/reverse proxy) before sharing the
URL with anyone**. It ships with no login of its own. See
`docs/ASSUMPTIONS.md` §10.4 for more on this before any real rollout.

## How the sample data demonstrates the model

`data/employees_sample.csv` has 30 employees, deliberately constructed so
every code path in the model fires at least once:

| Employee(s) | Demonstrates |
|---|---|
| David Okafor, Brandon Wells, Miguel Santos, Liam O'Connor | Below range minimum (priority 1) |
| Maria Chen, Ava Thompson, Sophia Nguyen | High performer significantly underpositioned (priority 2), incl. one with a recruiter-contact retention note |
| Priya Natarajan, Sophia Nguyen | Critical role + high flight risk together |
| Ella Moore, Owen Baker | Above the range maximum |
| Noah Peterson, Mia Rodriguez | Internal pay-equity flags (one overpaid-vs-performance, one underpaid-vs-peers) |
| Henry Scott, Zoe Adams | Supervisor-vs-objective rating divergence, in both directions |
| James Wright | Paid at range max despite mediocre performance - a governance/review case, not a raise case |
| The rest | A spread of ordinary "appropriately positioned" and "monitor" cases across departments, so the department/tier/priority charts have realistic shape |

Try switching the budget scenario (No fixed budget → try a small Fixed
budget, e.g. $50,000, and watch which employees get deferred first) and
adjusting a weight or two to see the whole table and charts recompute.

## Documentation (deliverables 1-7, 10)

| Doc | Covers |
|---|---|
| [`docs/DATA_STRUCTURE.md`](docs/DATA_STRUCTURE.md) | Source tables (deliverable 1) |
| [`docs/FORMULAS.md`](docs/FORMULAS.md) | All formulas & calculation logic (deliverable 2) |
| [`docs/SCORING_MODEL.md`](docs/SCORING_MODEL.md) | Performance scoring/weighting model (deliverable 3) |
| [`docs/RAISE_PRIORITIZATION.md`](docs/RAISE_PRIORITIZATION.md) | Raise-prioritization framework + budget scenarios (deliverable 4) |
| [`docs/FLIGHT_RISK_MODEL.md`](docs/FLIGHT_RISK_MODEL.md) | Flight-risk scoring framework (deliverable 5) |
| [`docs/DASHBOARD_LAYOUT.md`](docs/DASHBOARD_LAYOUT.md) | Dashboard layout, charts, filters (deliverables 6, 7) |
| [`docs/ASSUMPTIONS.md`](docs/ASSUMPTIONS.md) | Missing information, assumptions, limitations (deliverable 10) |

This README (build instructions) and `data/employees_sample.csv` (sample
data walkthrough above) cover deliverables 8 and 9.

## Governance guardrails built in

- Supervisor ratings and objective performance scores are kept in separate
  columns everywhere and only ever combined into a labeled "combined score."
- Performance is one input among several (position-in-range, tenure,
  criticality, flight risk, equity) - never the sole driver of a raise.
- Pay-equity gaps (manual flag or computed peer-group gap) are surfaced for
  HR/compensation review - the tool never renders a legal determination.
- No protected characteristic is collected or used anywhere in the model.
- HR overrides require a written justification and are stored alongside
  (never over) the system's original recommendation, for audit.
- Rows missing required fields are excluded from calculations and listed
  explicitly rather than guessed at; rows missing optional fields are
  included but flagged as less reliable.
