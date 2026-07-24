# 6. Dashboard layout, charts & filters

## 6.1 Page layout (top to bottom)

1. **Header** - title, "as of" date, Export CSV, Reset demo data.
2. **KPI stat tiles** - total current payroll, recommended raise budget
   (current scenario), overall payroll increase %, deferred amount, below-min
   count, above-max count, compa-ratio-below-threshold count, high/critical
   flight-risk count, equity concerns, recommendations needing review,
   incomplete/unreliable records. Tiles turn amber/red when the count is
   non-zero and worth attention.
3. **Charts** (dashboard summaries - see §6.2).
4. **Scenario planning & adjustable weights** (collapsible, open by
   default) - budget scenario picker, and every adjustable weight/threshold
   in the model, grouped by what it drives.
5. **Governance & data-quality flags** (collapsible) - the fixed governance
   statements, plus any employee rows excluded for missing required fields
   or included-but-flagged for missing optional fields.
6. **Employee-level detail** - filter toolbar + the full table (§6.4).
7. **Add / edit employee** (collapsible) - the input form. An "Edit" button
   on any row prefills it.
8. **HR override** (collapsible) - override form. An "Override" button on
   any row prefills the employee ID and shows the current system
   recommendation for reference.
9. **Reference: SaaS/web-hosting pay bands** (collapsible, closed by
   default) - the market-reference table.

Collapsible sections use native `<details>` elements so the page works
without JavaScript for reading; JS only adds chart rendering, live
filtering, and form-prefill convenience.

## 6.2 Charts (all required "dashboard summaries" charts)

| Chart | Type | What it shows |
|---|---|---|
| Recommended raises by department | Horizontal bar | Funded $ per department, current scenario |
| Recommended raises by performance level | Horizontal bar | Funded $ per performance tier |
| Recommended raises by priority | Horizontal bar | Funded $ per priority tier (1-7) |
| Immediate vs. phased adjustment cost | Horizontal bar | Two bars: immediate-cycle $ vs. phased (year-1 tranche) $ |
| Compa-ratio distribution, before vs. after | Grouped horizontal bar | Headcount per compa-ratio bucket (<85%, 85-95%, 95-105%, 105-115%, 115%+), before and after the current scenario's raises |
| Salary-position distribution, before vs. after | Grouped horizontal bar | Headcount per position category, before and after |
| Flight-risk distribution | Horizontal bar | Headcount per Low/Moderate/High/Critical rating |

All charts are hand-built inline SVG (no charting library dependency), with
hover tooltips, a legend whenever two series are shown, and value labels on
single-series charts. Colors follow a fixed categorical order (never
reassigned when a filter changes what's visible) and were chosen for
light/dark-mode contrast and colorblind-safe separation between adjacent
series.

## 6.3 Filters

Above the employee table: free-text search (name/department/role),
department dropdown, flight-risk dropdown, priority dropdown, and a
"needs review only" checkbox. All filtering happens client-side against
the already-rendered table (no page reload) so it stays fast at this scale;
at a much larger headcount this would move server-side/paginated.

## 6.4 Employee table columns

Employee, Role (job title + department/level), Current Salary, Range Min,
Range Mid, Range Max, Salary Position (% + category badge), Compa-Ratio,
Supervisor Rating, Objective Score, Combined Score (+ tier + divergence
badge), Flight Risk (rating + measurable/subjective sub-scores), Recommended
Raise % (+ override annotation), Recommended Raise $, Proposed New Salary,
New Compa-Ratio, New Position (% + category), Priority (tier + label),
Timing (Immediate/Phased + phase-2 detail), Business Justification, Requires
Review (Y/N + reasons on hover), and row actions (Edit / Override).

## 6.5 Why server-rendered instead of a JS framework

This mirrors the existing `org_chart_converter` tool in this repo: no build
step, no framework dependency, deployable the same way (plain Flask app,
optionally behind gunicorn, or via cPanel's Passenger integration - see the
root README). At real-company headcounts (hundreds to low thousands of
employees) this is more than fast enough; if you outgrow it, the calculation
engine (`calc.py`) is already decoupled from the web layer and can sit
behind an API for a richer front end without changing any formulas.
