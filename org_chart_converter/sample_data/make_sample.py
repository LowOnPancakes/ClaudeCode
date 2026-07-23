"""Generates sample_input.xlsx: a small, fully fictional demo dataset in the
expected 'Manager - Level N / Employee' shape, used to try the converter out."""
from pathlib import Path
from openpyxl import Workbook

ROWS = [
    ("All",) * 8,
    ("N/A", "All", "All", "All", "All", "All", "All", "All"),
    ("N/A", "N/A", "N/A", "N/A", "N/A", "N/A", "N/A", "Priya Chandra"),
    ("N/A", "N/A", "N/A", "N/A", "N/A", "N/A", "N/A", "Tomas Reyes"),
    ("Alex Nakamura", "All", "All", "All", "All", "All", "All", "All"),
    ("Alex Nakamura", "N/A", "All", "All", "All", "All", "All", "All"),
    ("Alex Nakamura", "N/A", "N/A", "N/A", "N/A", "N/A", "N/A", "Devon Ricci"),
    ("Alex Nakamura", "N/A", "N/A", "N/A", "N/A", "N/A", "N/A", "Marcus Webb"),
    ("Alex Nakamura", "Devon Ricci", "All", "All", "All", "All", "All", "All"),
    ("Alex Nakamura", "Devon Ricci", "N/A", "N/A", "N/A", "N/A", "N/A", "Sofia Marin"),
    ("Alex Nakamura", "Devon Ricci", "N/A", "N/A", "N/A", "N/A", "N/A", "Liam Okafor"),
    ("Alex Nakamura", "Marcus Webb", "All", "All", "All", "All", "All", "All"),
    ("Alex Nakamura", "Marcus Webb", "N/A", "N/A", "N/A", "N/A", "N/A", "Grace Lindqvist"),
]

HEADER = [f"Manager - Level {i}" for i in range(1, 8)] + ["Employee"]


def main():
    wb = Workbook()
    ws = wb.active
    ws.title = "sheet"
    ws.append(HEADER)
    for row in ROWS:
        ws.append(list(row))
    out = Path(__file__).parent / "sample_input.xlsx"
    wb.save(out)
    print(f"Wrote {out}")


if __name__ == "__main__":
    main()
