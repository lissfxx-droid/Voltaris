"""LCSC part-number lookup against the local jlcparts cache.sqlite3.

CLI:
    python lcsc_lookup.py mpn <MPN>
        Find by exact manufacturer part number.

    python lcsc_lookup.py detail <C编号>
        Get full info for a specific lcsc number (with or without 'C' prefix).

    python lcsc_lookup.py passive <category> <value> [package] [--basic]
        Find a passive component (resistor, capacitor, inductor) by parameters.

All commands output JSON to stdout for AI consumption. Exit 0 on success,
1 if no match found, 2 on error.

Schema (from jlcparts cache.sqlite3):
  components(lcsc INT PK, category_id, mfr, package, joints, manufacturer_id,
             basic, preferred, description, datasheet, stock, price, extra,
             jlc_extra, ...)
  categories(id, ...)
  manufacturers(id, ...)
"""

from __future__ import annotations

import json
import os
import sqlite3
import sys
from pathlib import Path
from typing import Any

DB_PATH = Path(
    os.environ.get(
        "JLCPARTS_DB",
        str(Path(__file__).parent.parent / "data" / "cache.sqlite3"),
    )
)


def open_db() -> sqlite3.Connection:
    if not DB_PATH.exists():
        print(
            f"ERROR: jlcparts database not found at {DB_PATH}\n"
            f"Set JLCPARTS_DB env var or download per backend/data/README.md",
            file=sys.stderr,
        )
        sys.exit(2)
    conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def lcsc_label(n: int) -> str:
    """Format integer lcsc as conventional 'C123456' string."""
    return f"C{n}"


def normalize_lcsc(s: str) -> int:
    """Accept 'C529355' or '529355', return integer."""
    s = s.strip().upper()
    if s.startswith("C"):
        s = s[1:]
    return int(s)


def row_to_part(row: sqlite3.Row) -> dict[str, Any]:
    """Common projection for AI output. Skips bulky fields like price/extra JSON
    unless explicitly requested via row_to_part_full."""
    return {
        "lcsc": lcsc_label(row["lcsc"]),
        "mfr": row["mfr"],
        "package": row["package"],
        "joints": row["joints"],
        "basic": bool(row["basic"]),
        "preferred": bool(row["preferred"]),
        "stock": row["stock"],
        "description": row["description"],
    }


# ---- queries ----------------------------------------------------------------

def find_by_mpn(conn: sqlite3.Connection, mpn: str, limit: int = 10) -> list[dict[str, Any]]:
    """Exact MPN match. Many MPNs map to multiple lcsc entries (different
    package variants), so we order by basic > preferred > stock so the most
    convenient pick comes first."""
    cur = conn.execute(
        """SELECT lcsc, mfr, package, joints, basic, preferred, stock, description
           FROM components
           WHERE mfr = ?
           ORDER BY basic DESC, preferred DESC, stock DESC
           LIMIT ?""",
        (mpn, limit),
    )
    return [row_to_part(r) for r in cur.fetchall()]


def find_passive(
    conn: sqlite3.Connection,
    category_keyword: str,
    value_keyword: str,
    package: str | None = None,
    prefer_basic: bool = True,
    limit: int = 10,
) -> list[dict[str, Any]]:
    """Find passive components (resistor / capacitor / inductor) by params.

    Strategy: avoid `JOIN + LIKE` on the 27GB components table (full scan).
    Instead:
      1. Look up matching category_ids in the tiny `categories` table.
      2. Filter `components` with `category_id IN (...)` (uses the existing
         components_category index → narrow to a few thousand rows).
      3. Apply description LIKE on that small subset.
    """
    keyword_lower = category_keyword.lower()
    cat_rows = conn.execute(
        "SELECT id FROM categories "
        "WHERE LOWER(category) LIKE ? OR LOWER(subcategory) LIKE ?",
        (f"%{keyword_lower}%", f"%{keyword_lower}%"),
    ).fetchall()
    cat_ids = [r["id"] for r in cat_rows]
    if not cat_ids:
        return []  # No category matches the keyword.

    placeholders = ",".join("?" * len(cat_ids))
    sql = (
        "SELECT lcsc, mfr, package, joints, basic, preferred, stock, description "
        f"FROM components WHERE category_id IN ({placeholders}) AND stock > 0"
    )
    args: list[Any] = list(cat_ids)
    if value_keyword:
        sql += " AND LOWER(description) LIKE ?"
        args.append(f"%{value_keyword.lower()}%")
    if package:
        sql += " AND package = ?"
        args.append(package)
    sql += (
        " ORDER BY basic DESC, preferred DESC, stock DESC"
        if prefer_basic
        else " ORDER BY preferred DESC, stock DESC"
    )
    sql += " LIMIT ?"
    args.append(limit)
    cur = conn.execute(sql, args)
    return [row_to_part(r) for r in cur.fetchall()]


def get_part_detail(conn: sqlite3.Connection, lcsc: str | int) -> dict[str, Any] | None:
    n = normalize_lcsc(str(lcsc))
    cur = conn.execute(
        """SELECT c.lcsc, c.mfr, c.package, c.joints, c.basic, c.preferred,
                  c.stock, c.description, c.datasheet, c.price, c.extra
           FROM components c WHERE c.lcsc = ?""",
        (n,),
    )
    row = cur.fetchone()
    if row is None:
        return None
    out = row_to_part(row)
    out["datasheet"] = row["datasheet"]
    # price and extra are JSON strings; pass through raw — let caller parse.
    out["price_raw"] = row["price"]
    out["extra_raw"] = row["extra"]
    return out


# ---- CLI --------------------------------------------------------------------

USAGE = """\
usage:
  lcsc_lookup.py mpn <MPN>
  lcsc_lookup.py detail <C编号>
  lcsc_lookup.py passive <category> <value> [package] [--basic]

examples:
  lcsc_lookup.py mpn STM32G431CBT6
  lcsc_lookup.py detail C529355
  lcsc_lookup.py passive Resistor 10kohm 0603 --basic
  lcsc_lookup.py passive Capacitor 100nF 0603

env:
  JLCPARTS_DB   override path to cache.sqlite3 (default: ../data/cache.sqlite3)
"""


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(USAGE, file=sys.stderr)
        return 2

    cmd = argv[1]
    conn = open_db()
    try:
        if cmd == "mpn":
            if len(argv) < 3:
                print("missing MPN", file=sys.stderr)
                return 2
            results = find_by_mpn(conn, argv[2])
            print(json.dumps({"query": {"mpn": argv[2]}, "results": results},
                             ensure_ascii=False, indent=2))
            return 0 if results else 1

        elif cmd == "detail":
            if len(argv) < 3:
                print("missing lcsc number", file=sys.stderr)
                return 2
            try:
                detail = get_part_detail(conn, argv[2])
            except ValueError:
                print(f"BAD_LCSC: '{argv[2]}'", file=sys.stderr)
                return 2
            print(json.dumps({"query": {"lcsc": argv[2]}, "result": detail},
                             ensure_ascii=False, indent=2))
            return 0 if detail else 1

        elif cmd == "passive":
            if len(argv) < 4:
                print("usage: passive <category> <value> [package] [--basic]",
                      file=sys.stderr)
                return 2
            category = argv[2]
            value = argv[3]
            package: str | None = None
            prefer_basic = "--basic" in argv
            for a in argv[4:]:
                if not a.startswith("--"):
                    package = a
                    break
            results = find_passive(conn, category, value, package, prefer_basic)
            print(json.dumps(
                {"query": {"category": category, "value": value,
                           "package": package, "prefer_basic": prefer_basic},
                 "results": results},
                ensure_ascii=False, indent=2,
            ))
            return 0 if results else 1

        else:
            print(USAGE, file=sys.stderr)
            return 2
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
