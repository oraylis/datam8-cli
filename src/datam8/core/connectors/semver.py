from __future__ import annotations

import re
from dataclasses import dataclass

from datam8.core.errors import Datam8ValidationError

_SEMVER_RE = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:[-+].*)?$")


@dataclass(frozen=True, order=True)
class SemVer:
    major: int
    minor: int
    patch: int

    @staticmethod
    def parse(raw: str) -> SemVer:
        v = (raw or "").strip()
        m = _SEMVER_RE.match(v)
        if not m:
            raise Datam8ValidationError(message="Invalid semver.", details={"version": raw})
        return SemVer(int(m.group(1)), int(m.group(2)), int(m.group(3)))


def _upper_bound_for_caret(v: SemVer) -> SemVer:
    # Semver caret:
    # ^1.2.3 := >=1.2.3 <2.0.0
    # ^0.2.3 := >=0.2.3 <0.3.0
    # ^0.0.3 := >=0.0.3 <0.0.4
    if v.major > 0:
        return SemVer(v.major + 1, 0, 0)
    if v.minor > 0:
        return SemVer(0, v.minor + 1, 0)
    return SemVer(0, 0, v.patch + 1)


def _upper_bound_for_tilde(v: SemVer) -> SemVer:
    # ~1.2.3 := >=1.2.3 <1.3.0
    # ~0.2.3 := >=0.2.3 <0.3.0
    return SemVer(v.major, v.minor + 1, 0)


def _parse_comparators(req: str) -> list[tuple[str, SemVer]]:
    parts = [p.strip() for p in req.split(",") if p.strip()]
    out: list[tuple[str, SemVer]] = []
    for p in parts:
        op = None
        for cand in (">=", "<=", "==", ">", "<"):
            if p.startswith(cand):
                op = cand
                raw_ver = p[len(cand) :].strip()
                out.append((cand, SemVer.parse(raw_ver)))
                break
        if op is None:
            raise Datam8ValidationError(message="Invalid version range comparator.", details={"part": p, "range": req})
    return out


def semver_satisfies(*, version: str, requirement: str | None) -> bool:
    req = (requirement or "").strip()
    if not req:
        return True
    v = SemVer.parse(version)

    if req.startswith("^"):
        base = SemVer.parse(req[1:].strip())
        upper = _upper_bound_for_caret(base)
        return v >= base and v < upper
    if req.startswith("~"):
        base = SemVer.parse(req[1:].strip())
        upper = _upper_bound_for_tilde(base)
        return v >= base and v < upper

    if any(req.startswith(op) for op in (">=", "<=", "==", ">", "<")) or "," in req:
        for op, bound in _parse_comparators(req):
            if op == ">=" and not (v >= bound):
                return False
            if op == "<=" and not (v <= bound):
                return False
            if op == ">" and not (v > bound):
                return False
            if op == "<" and not (v < bound):
                return False
            if op == "==" and not (v == bound):
                return False
        return True

    # Exact match (e.g. "1.2.3")
    return v == SemVer.parse(req)

