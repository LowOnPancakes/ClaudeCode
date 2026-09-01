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


def test_metadata_columns_after_employee(tmp_path):
    header = ["Manager - Level 1", "Employee", "Title", "Department"]
    rows = [
        ("All", "All", None, None),
        ("N/A", "Bob Lyons", "CEO", "Executive"),
        ("Bob Lyons", "Ben Reich", "CFO", "Finance"),
    ]
    path = make_workbook(tmp_path, rows, header=header)
    result = parse_workbook(path)
    roots = build_forest(result)

    assert result.attr_headers == ["Title", "Department"]
    assert roots == ["Bob Lyons"]
    assert result.attributes["Bob Lyons"] == {"Title": "CEO", "Department": "Executive"}
    assert result.attributes["Ben Reich"] == {"Title": "CFO", "Department": "Finance"}
    # rollup row (Employee="All") must not pollute attributes
    assert "All" not in result.attributes


def test_no_metadata_columns_still_works(tmp_path):
    # Old-style file: Employee is the last column, nothing trailing it.
    rows = [
        ("N/A", "Bob Lyons"),
        ("Bob Lyons", "Ben Reich"),
    ]
    path = make_workbook(tmp_path, rows)
    result = parse_workbook(path)
    roots = build_forest(result)

    assert result.attr_headers == []
    assert result.attributes == {}
    assert roots == ["Bob Lyons"]


def test_missing_employee_header_raises(tmp_path):
    rows = [("N/A", "Bob Lyons")]
    path = make_workbook(tmp_path, rows, header=["Manager - Level 1", "Person"])
    try:
        parse_workbook(path)
        assert False, "expected ValueError"
    except ValueError as e:
        assert "Employee" in str(e)


# employee_id, employee_legal_name, role_state, title, employment_type,
# department_id, department, current_entity, manager_id, manager_legal_name,
# manager_level_2, top_level_leader
FORMAT_B_HEADER = [
    "employee_id", "employee_legal_name", "role_state", "title",
    "employment_type", "department_id", "department", "current_entity",
    "manager_id", "manager_legal_name", "manager_level_2", "top_level_leader",
]

BOB_ROW = ("E1", "Bob Lyons", "Active", "CEO", "Salaried",
           "D1", "Executive", "Liquid Web LLC",
           None, None, None, "Bob Lyons")
BEN_ROW = ("E2", "Ben Reich", "Active", "CFO", "Salaried",
           "D1", "Executive", "Liquid Web LLC",
           "E1", "Bob Lyons", None, "Bob Lyons")
CALEB_ROW = ("E3", "Caleb Salazar", "Active", "VP", "Salaried",
             "D2", "Finance", "Liquid Web LLC",
             "E2", "Ben Reich", "Bob Lyons", "Bob Lyons")


def test_format_b_basic_hierarchy(tmp_path):
    path = make_workbook(tmp_path, [BOB_ROW, BEN_ROW, CALEB_ROW], header=FORMAT_B_HEADER)
    result = parse_workbook(path)
    roots = build_forest(result)

    assert roots == ["Bob Lyons"]
    assert result.children_of["Bob Lyons"] == ["Ben Reich"]
    assert result.children_of["Ben Reich"] == ["Caleb Salazar"]
    assert result.parent_of["Caleb Salazar"] == "Ben Reich"
    assert not result.warnings


def test_format_b_drops_id_and_top_level_leader_columns(tmp_path):
    path = make_workbook(tmp_path, [BOB_ROW], header=FORMAT_B_HEADER)
    result = parse_workbook(path)

    for forbidden in ("employee_id", "department_id", "manager_id", "top_level_leader"):
        assert forbidden not in result.attr_headers


def test_format_b_drops_role_state(tmp_path):
    path = make_workbook(tmp_path, [BOB_ROW], header=FORMAT_B_HEADER)
    result = parse_workbook(path)

    assert "role_state" not in result.attr_headers
    assert "role_state" not in result.attributes["Bob Lyons"]


def test_format_b_priority_columns_land_last_in_requested_order(tmp_path):
    # Regression test: "current_entity" (underscored) must match the
    # "current entity" normalized header, not silently fall through to the
    # leftover bucket ahead of department/title.
    path = make_workbook(tmp_path, [BOB_ROW], header=FORMAT_B_HEADER)
    result = parse_workbook(path)

    assert result.attr_headers[-3:] == ["department", "current_entity", "title"]
    # unrequested leftover columns are still carried through, just earlier
    assert set(result.attr_headers[:-3]) == {"employment_type"}
    assert result.attributes["Bob Lyons"]["current_entity"] == "Liquid Web LLC"
    assert result.attributes["Bob Lyons"]["department"] == "Executive"
    assert result.attributes["Bob Lyons"]["title"] == "CEO"


def test_format_b_root_has_blank_manager_chain(tmp_path):
    path = make_workbook(tmp_path, [BOB_ROW], header=FORMAT_B_HEADER)
    result = parse_workbook(path)
    roots = build_forest(result)

    assert roots == ["Bob Lyons"]
    assert result.parent_of["Bob Lyons"] is None


# Rippling-style naming variant: employee column literally named "employee"
# (would otherwise collide with Format A detection), manager_1/manager_2
# instead of manager_legal_name/manager_level_2, top_level_manager instead
# of top_level_leader, and "entity" instead of "current_entity".
RIPPLING_HEADER = [
    "employee", "title", "department", "job_family", "job_level", "entity",
    "manager_2", "manager_3", "top_level_manager", "role_state", "manager_1",
]

RIPPLING_ROOT = ("Robert Lyons", "CEO", "Executive", "Business Operations",
                  "Level 0", "Liquid Web LLC", None, None, None, "Active", None)
RIPPLING_CFO = ("Benjamin Reich", "CFO", "Executive", "Finance", "Level 1",
                 "Liquid Web LLC", None, None, "Robert Lyons", "Active", "Robert Lyons")
RIPPLING_IC = ("Aaron Bell", "Engineer", "Development", "Engineering", "Level 5",
               "Liquid Web LLC", "Robert Lyons", None, "Robert Lyons", "Active", "Benjamin Reich")


def test_rippling_style_naming_is_detected_as_format_b(tmp_path):
    path = make_workbook(tmp_path, [RIPPLING_ROOT, RIPPLING_CFO, RIPPLING_IC], header=RIPPLING_HEADER)
    result = parse_workbook(path)
    roots = build_forest(result)

    assert roots == ["Robert Lyons"]
    assert result.parent_of["Benjamin Reich"] == "Robert Lyons"
    assert result.parent_of["Aaron Bell"] == "Benjamin Reich"
    assert not result.warnings

    # manager_1/manager_2/top_level_manager consumed as chain, never metadata
    for forbidden in ("manager_1", "manager_2", "manager_3", "top_level_manager", "role_state"):
        assert forbidden not in result.attr_headers

    # "entity" fills the current_entity/entity priority slot, still last
    assert result.attr_headers[-3:] == ["department", "entity", "title"]
    assert result.attributes["Robert Lyons"]["entity"] == "Liquid Web LLC"
