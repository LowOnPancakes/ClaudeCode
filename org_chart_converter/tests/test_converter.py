import sys
from pathlib import Path

from openpyxl import Workbook

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from org_chart_converter import parse_workbook, build_forest, max_depth  # noqa: E402


def make_workbook(tmp_path, rows, header=None):
    wb = Workbook()
    ws = wb.active
    ncols = max(len(r) for r in rows)
    header = header or [f"Manager - Level {i + 1}" for i in range(ncols - 1)] + ["Employee"]
    ws.append(header)
    for r in rows:
        ws.append(list(r) + [None] * (ncols - len(r)))
    path = tmp_path / "sample.xlsx"
    wb.save(path)
    return path


def test_basic_hierarchy(tmp_path):
    rows = [
        ("All", "All", "All"),
        ("N/A", "All", "All"),
        ("N/A", "N/A", "Dick Faulkner"),
        ("Bob Lyons", "All", "All"),
        ("Bob Lyons", "N/A", "Ben Reich"),
        ("Bob Lyons", "N/A", "N/A"),  # rollup, should be skipped (filler leaf)
    ]
    path = make_workbook(tmp_path, rows)
    result = parse_workbook(path)
    roots = build_forest(result)

    assert set(roots) == {"Bob Lyons", "Dick Faulkner"}
    assert result.children_of["Bob Lyons"] == ["Ben Reich"]
    assert result.parent_of["Ben Reich"] == "Bob Lyons"
    assert result.parent_of["Dick Faulkner"] is None
    assert result.rows_used == 2  # only the two real-name leaf rows count


def test_multi_level_chain_and_manager_fallback(tmp_path):
    rows = [
        ("Bob Lyons", "Ben Reich", "Caleb Salazar", "N/A", "Brian McMahon"),
        ("Bob Lyons", "Ben Reich", "Caleb Salazar", "Brian McMahon", "Ian Cash"),
    ]
    path = make_workbook(tmp_path, rows)
    result = parse_workbook(path)
    roots = build_forest(result)

    assert roots == ["Bob Lyons"]
    assert result.children_of["Bob Lyons"] == ["Ben Reich"]
    assert result.children_of["Ben Reich"] == ["Caleb Salazar"]
    assert result.children_of["Caleb Salazar"] == ["Brian McMahon"]
    assert result.children_of["Brian McMahon"] == ["Ian Cash"]
    assert max_depth(result, roots) == 4


def test_conflicting_parent_generates_warning(tmp_path):
    rows = [
        ("Manager A", "N/A", "Employee X"),
        ("Manager B", "N/A", "Employee X"),
    ]
    path = make_workbook(tmp_path, rows)
    result = parse_workbook(path)

    assert len(result.warnings) == 1
    assert "Employee X" in result.warnings[0]
    # first-seen parent wins
    assert result.parent_of["Employee X"] == "Manager A"


def test_case_insensitive_filler(tmp_path):
    rows = [
        ("all", "n/a", "Employee Y"),
        ("Manager Z", "na", "Employee W"),
    ]
    path = make_workbook(tmp_path, rows)
    result = parse_workbook(path)
    roots = build_forest(result)

    assert "Employee Y" in roots
    assert result.parent_of["Employee W"] == "Manager Z"
