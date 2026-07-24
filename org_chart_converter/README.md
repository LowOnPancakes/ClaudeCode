# Org Chart Converter

Converts a flat "Manager - Level N / Employee" Excel export into a clean,
staircase-style org chart workbook — one column per reporting level, with
collapsible leadership groups built in.

## Input format

The script expects a worksheet shaped like this (any number of manager-level
columns is fine, the last column is always the individual's name):

| Manager - Level 1 | Manager - Level 2 | ... | Employee       |
|--------------------|--------------------|-----|----------------|
| All                | All                | ... | All            |
| N/A                | All                | ... | All            |
| N/A                | N/A                | ... | Aprille Tiedra |
| Bob Lyons          | N/A                | ... | Ben Reich      |
| Bob Lyons          | Ben Reich          | ... | Caleb Salazar  |

Rules the parser uses:

- The **last column** holds one person's name for that row.
- Every other column is that person's manager chain, read left to right.
- `All`, `N/A` (any case) and blank cells are placeholders and are ignored.
- A row where the last column is a placeholder is a rollup/summary row and
  is skipped — it doesn't add any information not already in other rows.
- A person's manager is the last real name in their chain. An empty chain
  means the person is a root (top of the org, no manager in this data).

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
