#!/usr/bin/env python3
"""
Browser front-end for org_chart_converter.py.

Anyone on the team opens this in a browser, drops in a "Manager - Level N /
Employee" style Excel export, and gets back:
  - an interactive, collapsible org chart right on the page
  - a "Download Excel wireframe" link (the same staircase workbook the CLI
    produces), generated in memory - nothing is written to disk on the server.

Run:
    pip install -r requirements.txt
    python app.py
Then open http://localhost:5000 (or the server's address, for team-wide access).
"""
import base64
import io
import os
import sys
from html import escape

from flask import Flask, render_template, request

_HERE = os.path.dirname(os.path.abspath(__file__))
# org_chart_converter.py normally lives one directory up (repo layout), but
# some deployment methods (e.g. cPanel's Setup Python App) flatten everything
# into one directory - support both.
sys.path.insert(0, _HERE)
sys.path.insert(0, os.path.join(_HERE, ".."))
from org_chart_converter import build_forest, max_depth, parse_workbook, write_org_chart  # noqa: E402

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 25 * 1024 * 1024  # 25 MB upload cap


def count_descendants(children_of, name):
    total = 0
    for child in children_of.get(name, []):
        total += 1 + count_descendants(children_of, child)
    return total


def render_node_html(name, children_of, attributes, depth=0):
    kids = children_of.get(name, [])
    safe_name = escape(name)
    data_name = escape(name.lower())

    attrs = attributes.get(name)
    tooltip = ""
    if attrs:
        parts = [f"{k}: {v}" for k, v in attrs.items() if v not in (None, "")]
        if parts:
            tooltip = f' title="{escape(" | ".join(parts))}"'

    if not kids:
        return f'<div class="node leaf" data-name="{data_name}"{tooltip}>{safe_name}</div>'

    count = count_descendants(children_of, name)
    badge = f'{count} report{"s" if count != 1 else ""}'
    inner = "".join(render_node_html(k, children_of, attributes, depth + 1) for k in kids)
    open_attr = " open" if depth == 0 else ""
    return (
        f'<div class="node manager" data-name="{data_name}">'
        f"<details{open_attr}>"
        f'<summary{tooltip}>{safe_name} <span class="badge">{badge}</span></summary>'
        f'<div class="children">{inner}</div>'
        f"</details></div>"
    )


@app.route("/", methods=["GET"])
def index():
    return render_template("index.html")


@app.route("/convert", methods=["POST"])
def convert():
    file = request.files.get("file")
    if not file or file.filename == "":
        return render_template("index.html", error="Please choose an .xlsx file.")

    sheet_name = request.form.get("sheet") or None

    try:
        result = parse_workbook(file, sheet_name=sheet_name)
        roots = build_forest(result)
        if not roots:
            raise ValueError("No root (top-of-org) people found - check the file format.")
    except Exception as e:
        return render_template("index.html", error=f"Couldn't process that file: {e}")

    depth = max_depth(result, roots)
    tree_html = "".join(
        render_node_html(r, result.children_of, result.attributes, depth=0) for r in roots
    )

    buf = io.BytesIO()
    write_org_chart(result, roots, buf, source_name=file.filename)
    buf.seek(0)
    xlsx_b64 = base64.b64encode(buf.read()).decode("ascii")

    base = file.filename.rsplit(".", 1)[0] if "." in file.filename else file.filename
    stats = {
        "source": file.filename,
        "rows_read": result.rows_read,
        "rows_used": result.rows_used,
        "people": len(result.all_names),
        "roots": len(roots),
        "depth": depth + 1,
        "warnings": result.warnings,
        "attr_headers": result.attr_headers,
    }
    return render_template(
        "index.html",
        tree_html=tree_html,
        stats=stats,
        xlsx_b64=xlsx_b64,
        download_name=f"{base}_wireframe.xlsx",
    )


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
