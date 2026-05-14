"""CircuitIR validator (CircuitIR.md v1.0).

CLI:
    python validate.py path/to/circuit.thinir.yaml

Exit code 0 = valid, non-zero = at least one error.
Errors are printed to stdout, one per line, prefixed with the rule that fired.

There is no warning level — every check is hard-fail (per CircuitIR spec §2.3).
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import yaml


# Allowed top-level keys per spec §3.
ALLOWED_TOP_LEVEL = {
    "schema_version",
    "project",
    "parts",
    "nets",
    "modules",
    "buses",
}

# Forbidden anywhere in the document (spec §2.1). Any nested occurrence fails.
FORBIDDEN_FIELD_NAMES = {
    "notes",
    "assumptions",
    "warnings",
    "todos",
    "confidence",
    "defaults",
    "role",
    "topology",
}


def load_yaml(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def find_forbidden(node: Any, path: str = "$") -> list[str]:
    """Walk the document and report any forbidden field names."""
    errs: list[str] = []
    if isinstance(node, dict):
        for k, v in node.items():
            if k in FORBIDDEN_FIELD_NAMES:
                errs.append(f"FORBIDDEN_FIELD: '{k}' at {path}")
            errs.extend(find_forbidden(v, f"{path}.{k}"))
    elif isinstance(node, list):
        for i, item in enumerate(node):
            errs.extend(find_forbidden(item, f"{path}[{i}]"))
    return errs


def check_top_level(ir: dict[str, Any]) -> list[str]:
    errs: list[str] = []
    if not isinstance(ir, dict):
        errs.append("STRUCTURE: top-level must be a mapping")
        return errs
    for k in ir.keys():
        if k not in ALLOWED_TOP_LEVEL:
            errs.append(f"UNKNOWN_TOP_KEY: '{k}' (only {sorted(ALLOWED_TOP_LEVEL)} allowed)")
    if ir.get("schema_version") != "1.0":
        errs.append(f"SCHEMA_VERSION: must be '1.0', got {ir.get('schema_version')!r}")
    if "project" not in ir or not isinstance(ir.get("project"), dict):
        errs.append("PROJECT_MISSING: top-level 'project' mapping required")
    elif "name" not in ir["project"]:
        errs.append("PROJECT_NAME_MISSING: project.name required")
    return errs


def check_parts(ir: dict[str, Any]) -> list[str]:
    """Each part must have lcsc OR mpn (spec §2.2)."""
    errs: list[str] = []
    parts = ir.get("parts")
    if not isinstance(parts, dict):
        errs.append("PARTS_MISSING: top-level 'parts' mapping required")
        return errs
    if not parts:
        errs.append("PARTS_EMPTY: at least one part required")
    for ref, p in parts.items():
        if not isinstance(p, dict):
            errs.append(f"PART_STRUCTURE: parts.{ref} must be a mapping")
            continue
        if "lcsc" not in p and "mpn" not in p:
            errs.append(f"PART_NO_LCSC_OR_MPN: parts.{ref} missing both lcsc and mpn")
    return errs


def _split_pinref(pinref: str) -> tuple[str, str] | None:
    """Parse '<REF>.<PIN>'. Returns (ref, pin) or None on malformed."""
    if not isinstance(pinref, str) or "." not in pinref:
        return None
    ref, pin = pinref.split(".", 1)
    if not ref or not pin:
        return None
    return ref, pin


def check_nets(ir: dict[str, Any]) -> list[str]:
    """Spec §2.2/§2.3: every net resolves to known parts; every pin appears
    in exactly one net across the whole document."""
    errs: list[str] = []
    nets = ir.get("nets")
    if not isinstance(nets, dict):
        errs.append("NETS_MISSING: top-level 'nets' mapping required")
        return errs
    if not nets:
        errs.append("NETS_EMPTY: at least one net required")

    parts = ir.get("parts", {}) if isinstance(ir.get("parts"), dict) else {}
    seen_pins: dict[str, str] = {}  # pinref → first net that used it

    for net_name, pins in nets.items():
        if not isinstance(pins, list):
            errs.append(f"NET_STRUCTURE: nets.{net_name} must be a list of pinrefs")
            continue
        if len(pins) < 2:
            errs.append(f"NET_TOO_FEW: nets.{net_name} has < 2 endpoints")
        for pinref in pins:
            parsed = _split_pinref(pinref)
            if parsed is None:
                errs.append(f"PIN_MALFORMED: nets.{net_name} entry {pinref!r}")
                continue
            ref, _pin = parsed
            if ref not in parts:
                errs.append(f"NET_UNKNOWN_REF: nets.{net_name} → {pinref} (ref {ref} not in parts)")
            if pinref in seen_pins:
                errs.append(
                    f"PIN_DUPLICATE: {pinref} appears in nets.{seen_pins[pinref]} "
                    f"AND nets.{net_name}"
                )
            else:
                seen_pins[pinref] = net_name
    return errs


def check_modules(ir: dict[str, Any]) -> list[str]:
    """Spec §2.3: modules.<id>.parts must reference known parts."""
    errs: list[str] = []
    modules = ir.get("modules")
    if modules is None:
        return errs  # optional
    if not isinstance(modules, dict):
        errs.append("MODULES_STRUCTURE: 'modules' must be a mapping")
        return errs
    parts = ir.get("parts", {}) if isinstance(ir.get("parts"), dict) else {}
    for mid, m in modules.items():
        if not isinstance(m, dict) or "parts" not in m:
            errs.append(f"MODULE_STRUCTURE: modules.{mid} must have 'parts' list")
            continue
        for ref in m.get("parts", []):
            if ref not in parts:
                errs.append(f"MODULE_UNKNOWN_REF: modules.{mid} → unknown part {ref}")
    return errs


def check_buses(ir: dict[str, Any]) -> list[str]:
    """Spec §2.3: buses.<id>.signals values must reference known nets."""
    errs: list[str] = []
    buses = ir.get("buses")
    if buses is None:
        return errs  # optional
    if not isinstance(buses, dict):
        errs.append("BUSES_STRUCTURE: 'buses' must be a mapping")
        return errs
    nets = ir.get("nets", {}) if isinstance(ir.get("nets"), dict) else {}
    for bid, b in buses.items():
        if not isinstance(b, dict):
            errs.append(f"BUS_STRUCTURE: buses.{bid} must be a mapping")
            continue
        signals = b.get("signals", {})
        if not isinstance(signals, dict):
            errs.append(f"BUS_SIGNALS_STRUCTURE: buses.{bid}.signals must be a mapping")
            continue
        for role, net_name in signals.items():
            if net_name not in nets:
                errs.append(f"BUS_UNKNOWN_NET: buses.{bid}.signals.{role} → unknown net {net_name}")
    return errs


def validate(ir: Any) -> list[str]:
    """Run all checks. Returns a flat list of error strings (empty = valid)."""
    if not isinstance(ir, dict):
        return ["STRUCTURE: top-level must be a mapping"]
    errs: list[str] = []
    errs.extend(find_forbidden(ir))
    errs.extend(check_top_level(ir))
    errs.extend(check_parts(ir))
    errs.extend(check_nets(ir))
    errs.extend(check_modules(ir))
    errs.extend(check_buses(ir))
    return errs


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: validate.py <path/to/circuit.thinir.yaml>", file=sys.stderr)
        return 2
    path = Path(argv[1])
    if not path.exists():
        print(f"FILE_NOT_FOUND: {path}", file=sys.stderr)
        return 2
    try:
        ir = load_yaml(path)
    except yaml.YAMLError as e:
        print(f"YAML_PARSE_ERROR: {e}", file=sys.stderr)
        return 2
    errs = validate(ir)
    if not errs:
        print(f"OK: {path} is a valid CircuitIR (parts={len(ir.get('parts', {}))}, "
              f"nets={len(ir.get('nets', {}))})")
        return 0
    print(f"INVALID: {path} — {len(errs)} error(s):")
    for e in errs:
        print(f"  - {e}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
