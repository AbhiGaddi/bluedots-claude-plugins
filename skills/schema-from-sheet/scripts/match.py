"""Shared sheet-row -> network.json property matching.

Two passes so an exact title always wins: pass 1 pairs rows whose title (or the
cell's second line, the old label) names exactly one free property; pass 2 pairs
the rest by dependency (conditional variants -> the property whose x-show-if
holds that value) and finally by fuzzy title.
"""
import difflib
import re


def norm(t):
    return re.sub(r"[^a-z0-9]+", "", (t or "").lower())


def dep_values(dep):
    """Values named in a dependency, e.g. "if highest qualification = PU College" -> ["pucollege"]."""
    if "=" not in dep:
        return []
    rhs = dep.split("=", 1)[1]
    return [norm(p) for p in re.split(r"\bor\b|/|;|,|'", rhs) if norm(p)]


def dep_score(row, prop):
    show = prop.get("x-show-if")
    want = dep_values(row.get("dependency", ""))
    if not want or not isinstance(show, dict):
        return 0
    vals = {norm(v) for vs in show.values() for v in (vs if isinstance(vs, list) else [vs])}
    score = 0
    for w in want:
        if w in vals:
            score += 3
        elif any(len(w) > 3 and len(v) > 3 and (w in v or v in w) for v in vals):
            score += 1
    return score


def match_all(rows, props):
    """rows: sheet rows (dicts); props: [(key, prop)]. Returns {row index: ((key, prop), how)}."""
    by_title = {}
    for k, p in props:
        by_title.setdefault(norm(p.get("title", k)), []).append((k, p))
    out, taken = {}, set()
    # pass 1: exact title / old label
    for i, r in enumerate(rows):
        for t in (r.get("title"), r.get("subtitle", "")):
            hits = [h for h in by_title.get(norm(t), []) if h[0] not in taken]
            if len(hits) > 1 and r.get("dependency"):
                hits = sorted(hits, key=lambda h: -dep_score(r, h[1]))[:1] if dep_score(r, max(hits, key=lambda h: dep_score(r, h[1]))[1]) else []
            if hits:
                out[i] = (hits[0], "title")
                taken.add(hits[0][0])
                break
    # pass 2: dependency, then fuzzy title
    for i, r in enumerate(rows):
        if i in out:
            continue
        free = [(k, p) for k, p in props if k not in taken]
        if r.get("type") == "geo":
            locs = [h for h in free if "location" in h[1]]
            primary = "primary" in (r.get("map_discovery") or "").lower()
            locs.sort(key=lambda h: (h[1].get("location") == "primary") != primary)
            if locs:
                out[i] = (locs[0], "geo")
                taken.add(locs[0][0])
                continue
        best = max(free, key=lambda h: dep_score(r, h[1]), default=None)
        if best and dep_score(r, best[1]) > 0:
            out[i] = (best, "dependency")
            taken.add(best[0])
            continue
        names = {norm(p.get("title", k)): (k, p) for k, p in free}
        close = difflib.get_close_matches(norm(r.get("title")), list(names), n=1, cutoff=0.6)
        if close:
            out[i] = (names[close[0]], "fuzzy")
            taken.add(names[close[0]][0])
    return out
