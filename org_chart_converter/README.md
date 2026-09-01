# Org Chart Converter

Converts an org-structure Excel export into a clean, staircase-style org
chart workbook — one column per reporting level, with collapsible leadership
groups built in. Two source shapes are auto-detected from the header row.

## Input format

**Format A** — one row per manager-chain scope, ending in an "Employee"
column (any number of manager-level columns is fine):

| Manager - Level 1 | Manager - Level 2 | ... | Employee       |
|--------------------|--------------------|-----|----------------|
| All                | All                | ... | All            |
| N/A                | All                | ... | All            |
| N/A                | N/A                | ... | Aprille Tiedra |
| Bob Lyons          | N/A                | ... | Ben Reich      |
| Bob Lyons          | Ben Reich          | ... | Caleb Salazar  |

- The column headed exactly **"Employee"** holds one person's name for that
  row. Every column before it is that person's manager chain, read left to
  right. Every column after it is a per-person metadata field (Title,
  Department, ...) carried through to the output as-is.
- `All`, `N/A` (any case) and blank cells are placeholders and are ignored.
- A row where "Employee" is a placeholder is a rollup/summary row and is
  skipped — it doesn't add any information not already in other rows.
- A person's manager is the last real name in their chain. An empty chain
  means the person is a root (top of the org, no manager in this data).

**Format B** — one row per employee, with named ancestor columns going
upward. This shape is detected by the *pattern* of its manager-chain
columns, not by exact names — different exports of it use different naming,
and both are recognized automatically:

| employee_id | employee_legal_name | title | department_id | department | current_entity | manager_id | manager_legal_name | manager_level_2 | ... | top_level_leader |
|---|---|---|---|---|---|---|---|---|---|---|
| E1 | Bob Lyons | CEO | D1 | Executive | Liquid Web LLC | | | | | Bob Lyons |
| E2 | Ben Reich | CFO | D1 | Executive | Liquid Web LLC | E1 | Bob Lyons | | | Bob Lyons |

or, equally recognized (e.g. a Rippling export):

| employee | title | department | entity | manager_1 | manager_2 | ... | top_level_manager | role_state |
|---|---|---|---|---|---|---|---|---|
| Robert Lyons | CEO | Executive | Liquid Web LLC | | | | | Active |
| Benjamin Reich | CFO | Executive | Liquid Web LLC | Robert Lyons | | | Robert Lyons | Active |

- The employee-name column (`employee_legal_name` or `employee`) is renamed
  "Employee" and put first in the output.
- The direct-manager column (`manager_legal_name` or `manager_1`) is
  generation 1; `manager_level_2`/`manager_2`, `manager_level_3`/`manager_3`,
  etc. are each one generation further up. A blank cell ends the chain (that
  generation is the top).
- The top-of-org column (`top_level_leader` or `top_level_manager`) is
  dropped — it's redundant with whichever chain column already holds the
  top of the org.
- Any column with **`_id`** in its name is dropped, and so is `role_state`.
- Whichever columns match **`department`**, **`current_entity`**/`entity`,
  and **`title`** become metadata columns at the end of the output, in that
  order. Any other leftover column (e.g. `employment_type`, `job_family`) is
  still carried through, placed right before those three, rather than
  silently dropped.

If none of "Employee", "employee_legal_name", or a manager-chain column
pattern is found, the script raises a clear error naming what it was
looking for.

## Install

```bash
pip install -r requirements.txt
```

## Usage

```bash
python org_chart_converter.py path/to/report.xlsx -o wireframe.xlsx
```

- `-o/--output` is optional; defaults to `<input>_wireframe.xlsx`.
- `--sheet NAME` reads a specific worksheet instead of the active one.

## Output

A workbook with two sheets:

- **Org Chart** — column A always shows the row's person, no matter their
  depth, so you can scan or filter on a single column. From column B on, that
  same name is placed in whichever column matches their depth in the
  hierarchy, so the layout naturally "staircases" down and right the deeper
  you go. Rows carry Excel outline levels, so you can use Excel's native row
  grouping (the `+`/`-` buttons in the left margin, or *Data > Group*) to
  collapse or expand entire teams. Names with direct reports are bolded so
  leadership stands out at a glance. Any metadata columns from the source
  file (Title, Department, etc.) follow after the staircase.
- **Summary** — row counts, total people found, number of top-level roots,
  max depth, and any data warnings (e.g. someone listed under two different
  managers in the source file).

## Try it on the sample data

```bash
python sample_data/make_sample.py
python org_chart_converter.py sample_data/sample_input.xlsx
```

## Tests

```bash
pip install pytest
python -m pytest tests/
```

## Web app (browser access for the whole team)

`webapp/` has a Flask front-end over this same converter: drop a file in a
browser, get a collapsible org chart plus a download link for the wireframe
workbook - no local Python setup needed for whoever's using it. See
[`webapp/README.md`](webapp/README.md) for running it locally and deploying
it somewhere the team can reach.
