#!/usr/bin/env python3
"""
Convert a flat "Manager - Level N / Employee [/ metadata...]" Excel export
into a staircase-style org chart workbook with collapsible leadership
grouping.

Expected input shape (header row + data rows), any number of level columns,
and any number of trailing metadata columns after "Employee":

    Manager - Level 1 | ... | Employee       | Title  | Department | ...
    All               | ... | All            |        |            |
    N/A               | ... | Aprille Tiedra | Coord. | Support    | ...
    Bob Lyons         | ... | Ben Reich      | VP     | Sales      | ...
    ...

Rules:
  - The column headed exactly "Employee" (case-insensitive) holds an
    individual name for that row - a "leaf" for that row's manager chain.
  - Every column BEFORE "Employee" forms that person's manager chain, read
    left to right. Any number of these columns is supported.
  - Every column AFTER "Employee" is treated as a metadata field for that
    person (Title, Department, Employment type, Entity, ...) - whatever
    columns are present, in whatever order, get carried through to the
    output automatically. No fixed set of fields is assumed.
  - "All" and "N/A" (any case) and blank cells are filler/placeholder values
    in the manager-chain columns, not real names, and are ignored.
  - Rows whose "Employee" cell is filler are rollup/summary rows and are
    skipped; they carry no reporting-line information not already present
    in other rows (their metadata columns are typically junk/placeholder
    values on those synthetic rows, so they're skipped too).
  - A row's parent is the last real name in its manager chain. If the chain
    is empty, the person is a root (top of the org / no manager in this data).

Usage:
    python org_chart_converter.py INPUT.xlsx [-o OUTPUT.xlsx]
"""
import argparse
import sys
from openpyxl import load_workbook, Workbook
from openpyxl.styles import Font, PatternFill, Alignment
from openpyxl.utils import get_column_letter

FILLER = {"", "all", "n/a", "na", "none"}
EMPLOYEE_HEADER = "employee"


def is_filler(value):
    if value is None:
        return True
    return str(value).strip().lower() in FILLER


def clean(value):
    return str(value).strip()


class ParseResult:
    def __init__(self):
        self.parent_of = {}       # name -> parent name (or None for root)
        self.children_of = {}     # name -> ordered list of child names (dedup)
        self.all_names = set()
        self.warnings = []
        self.rows_read = 0
        self.rows_used = 0
        self.attr_headers = []    # ordered metadata column labels (may be empty)
        self.attributes = {}      # name -> {attr_header: value}

    def add_node(self, name):
        self.all_names.add(name)
        self.children_of.setdefault(name, [])

    def set_parent(self, child, parent):
        self.add_node(child)
        if parent is not None:
            self.add_node(parent)

        existing = self.parent_of.get(child, "__unset__")
        if existing == "__unset__":
            self.parent_of[child] = parent
            if parent is not None:
                siblings = self.children_of[parent]
                if child not in siblings:
                    siblings.append(child)
        elif existing != parent:
            self.warnings.append(
                f'"{child}" appears under multiple managers: '
                f'"{existing}" and "{parent}" (kept "{existing}").'
            )

    def set_attributes(self, name, attrs):
        if not attrs:
            return
        existing = self.attributes.get(name)
        if existing is None:
            self.attributes[name] = attrs
        elif existing != attrs:
            self.warnings.append(
                f'"{name}" has conflicting metadata across rows '
                f"(kept the first occurrence)."
            )


def _find_employee_column(header):
    for i, cell in enumerate(header):
        if cell is not None and str(cell).strip().lower() == EMPLOYEE_HEADER:
            return i
    return None


def parse_workbook(path, sheet_name=None):
    wb = load_workbook(path, data_only=True)
    ws = wb[sheet_name] if sheet_name else wb.active

    rows = list(ws.iter_rows(values_only=True))
    if not rows:
        raise ValueError("Worksheet is empty.")

    header, *data_rows = rows
    if len(header) < 2:
        raise ValueError(
            "Expected at least 2 columns (one or more manager-level "
            "columns plus a final name column)."
        )

    employee_idx = _find_employee_column(header)
    if employee_idx is None:
        raise ValueError(
            'Could not find a column headed "Employee" in the header row. '
            "That column marks the split between the manager-chain columns "
            "and any per-person metadata columns."
        )

    attr_headers = [
        str(h).strip() for h in header[employee_idx + 1:] if h is not None and str(h).strip()
    ]
    n_attrs = len(attr_headers)

    result = ParseResult()
    result.attr_headers = attr_headers

    for row in data_rows:
        if row is None or all(c is None for c in row):
            continue
        result.rows_read += 1

        level_cells = row[:employee_idx]
        leaf_cell = row[employee_idx]
        attr_cells = row[employee_idx + 1:employee_idx + 1 + n_attrs]

        if is_filler(leaf_cell):
            continue  # rollup/summary row, no new information

        leaf_name = clean(leaf_cell)
        chain = [clean(c) for c in level_cells if not is_filler(c)]

        parent = chain[-1] if chain else None
        result.set_parent(leaf_name, parent)

        if attr_headers:
            attrs = {
                h: (v if v is not None else "")
                for h, v in zip(attr_headers, attr_cells)
            }
            result.set_attributes(leaf_name, attrs)

        # Also register manager-to-manager links within the chain itself,
        # as a fallback for data where a manager never gets its own leaf row.
        for i in range(len(chain) - 1):
            result.set_parent(chain[i + 1], chain[i])

        result.rows_used += 1

    return result


def build_forest(result):
    roots = [
        name for name in result.all_names
        if result.parent_of.get(name) is None
    ]
    roots.sort(key=str.lower)
    for parent in result.children_of:
        result.children_of[parent].sort(key=str.lower)
    return roots


def max_depth(result, roots):
    best = 0

    def walk(name, depth):
        nonlocal best
        best = max(best, depth)
        for child in result.children_of.get(name, []):
            walk(child, depth + 1)

    for r in roots:
        walk(r, 0)
    return best


HEADER_FILL = PatternFill("solid", fgColor="1F2937")
HEADER_FONT = Font(color="FFFFFF", bold=True, size=12)
MANAGER_FONT = Font(bold=True)
LEAF_FONT = Font(bold=False)
ROOT_FONT = Font(bold=True, size=13, color="1F4E78")


def write_org_chart(result, roots, out_path, source_name=""):
    wb = Workbook()
    ws = wb.active
    ws.title = "Org Chart"

    depth = max_depth(result, roots)
    staircase_cols = depth + 1
    attr_headers = result.attr_headers
    total_cols = staircase_cols + len(attr_headers)

    ws.cell(row=1, column=1, value=f"Org chart{(' - ' + source_name) if source_name else ''}")
    ws["A1"].font = HEADER_FONT
    for col in range(1, staircase_cols + 1):
        ws.cell(row=1, column=col).fill = HEADER_FILL

    for i, label in enumerate(attr_headers):
        cell = ws.cell(row=1, column=staircase_cols + 1 + i, value=label)
        cell.font = HEADER_FONT
        cell.fill = HEADER_FILL

    ws.row_dimensions[1].height = 22

    current_row = 2

    def write_node(name, col, depth_level):
        nonlocal current_row
        r = current_row
        cell = ws.cell(row=r, column=col, value=name)
        children = result.children_of.get(name, [])
        if depth_level == 0:
            cell.font = ROOT_FONT
        elif children:
            cell.font = MANAGER_FONT
        else:
            cell.font = LEAF_FONT

        if depth_level > 0:
            ws.row_dimensions[r].outline_level = min(depth_level, 7)

        attrs = result.attributes.get(name)
        if attrs:
            for i, header in enumerate(attr_headers):
                ws.cell(row=r, column=staircase_cols + 1 + i, value=attrs.get(header, ""))

        current_row += 1
        for child in children:
            write_node(child, col + 1, depth_level + 1)

    for root in roots:
        write_node(root, 1, 0)

    ws.sheet_properties.outlinePr.summaryBelow = False
    for col in range(1, total_cols + 1):
        ws.column_dimensions[get_column_letter(col)].width = 26
    ws.freeze_panes = "A2"

    # Summary sheet
    summary = wb.create_sheet("Summary")
    summary["A1"] = "Metric"
    summary["B1"] = "Value"
    summary["A1"].font = summary["B1"].font = Font(bold=True)
    stats = [
        ("Source file", source_name),
        ("Rows read", result.rows_read),
        ("Rows used", result.rows_used),
        ("Rows skipped (rollup/summary)", result.rows_read - result.rows_used),
        ("Total people", len(result.all_names)),
        ("Top-level roots", len(roots)),
        ("Max depth", depth + 1),
        ("Metadata columns detected", ", ".join(attr_headers) if attr_headers else "(none)"),
        ("Data warnings", len(result.warnings)),
    ]
    for i, (k, v) in enumerate(stats, start=2):
        summary.cell(row=i, column=1, value=k)
        summary.cell(row=i, column=2, value=v)
    summary.column_dimensions["A"].width = 32
    summary.column_dimensions["B"].width = 40

    if result.warnings:
        summary.cell(row=len(stats) + 3, column=1, value="Warnings").font = Font(bold=True)
        for i, w in enumerate(result.warnings, start=len(stats) + 4):
            summary.cell(row=i, column=1, value=w)

    wb.save(out_path)


def convert(input_path, output_path=None, sheet_name=None):
    result = parse_workbook(input_path, sheet_name=sheet_name)
    roots = build_forest(result)
    if not roots:
        raise ValueError("No root (top-of-org) people found - check the input format.")
    if output_path is None:
        output_path = input_path.rsplit(".", 1)[0] + "_wireframe.xlsx"
    write_org_chart(result, roots, output_path, source_name=input_path.split("/")[-1])
    return result, roots, output_path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", help="Path to the source .xlsx report")
    parser.add_argument("-o", "--output", help="Path to write the wireframe .xlsx to")
    parser.add_argument("--sheet", help="Worksheet name to read (defaults to the active sheet)")
    args = parser.parse_args()

    try:
        result, roots, output_path = convert(args.input, args.output, args.sheet)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    print(f"Read {result.rows_read} rows, used {result.rows_used}.")
    print(f"Found {len(result.all_names)} people, {len(roots)} top-level root(s), "
          f"max depth {max_depth(result, roots) + 1}.")
    if result.attr_headers:
        print(f"Metadata columns carried through: {', '.join(result.attr_headers)}")
    if result.warnings:
        print(f"{len(result.warnings)} data warning(s) - see the Summary sheet.")
    print(f"Wrote {output_path}")


if __name__ == "__main__":
    main()
