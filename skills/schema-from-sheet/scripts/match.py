"""Shared sheet-row -> network.json property matching.

A wrong pairing is worse than no pairing (its CHANGED attributes would be
false), so matching is conservative:
  pass 1  exact: title, description (where the question lives), the cell's
          second line (old label), or the property key ("Disability Type" ->
          disability_type)
  pass 2  conditional variants by dependency value (x-show-if)
  pass 3  fuzzy title, only when one candidate is clearly best
Anything else stays NEW / ORPHAN for a person to decide.
"""
import difflib
import re


def norm(t):
    t = (t or "").lower().replace("%", " percent ").replace("#", " number ").replace("&", " and ")
    t = t.replace("’", "'").replace("‘", "'")
    return re.sub(r"[^a-z0-9]+", "", t)


def dep_values(dep):
    """Values a dependency names, from every clause:
    "if X = PU College", "visible only if category chosen is RCI",
    "Organisation Type = Educational and Who can contact = Job Seekers"."""
    out = []
    for clause in re.split(r"\band\b|\n", dep or "", flags=re.I):
        m = re.search(r"(?:=|\bis\b|\bequals\b)\s*(.+)$", clause, re.I)
        if m:
            out += [norm(p) for p in re.split(r"\bor\b|/|;|,|'|\"", m.group(1)) if norm(p)]
    return out


def option_overlap(row, prop):
    """Share of the row's options found in the property's enum (0..1)."""
    opts = {norm(o) for o in row.get("options") or []}
    enum = prop.get("enum") or (prop.get("items") or {}).get("enum") or []
    if not opts or not enum:
        return 0.0
    return len(opts & {norm(e) for e in enum}) / len(opts)


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


def similarity(target, key, prop):
    return max(difflib.SequenceMatcher(None, target, norm(prop.get("title", ""))).ratio(),
               difflib.SequenceMatcher(None, target, norm(key)).ratio(),
               difflib.SequenceMatcher(None, target, norm(prop.get("description", ""))).ratio())


def match_all(rows, props):
    """rows: sheet rows (dicts); props: [(key, prop)]. Returns {row index: ((key, prop), how)}."""
    by_name = {}
    for k, p in props:
        # The sheet often carries the question ("What are you looking for?") that the
        # schema keeps in `description`, with a short `title` ("Looking For").
        for name in {norm(p.get("title", "")), norm(k), norm(p.get("description", ""))}:
            if name:
                by_name.setdefault(name, []).append((k, p))
    out, taken = {}, set()

    def free(hits):
        seen, res = set(), []
        for h in hits:
            if h[0] not in taken and h[0] not in seen:
                seen.add(h[0])
                res.append(h)
        return res

    # pass 1: exact title / old label / key
    for i, r in enumerate(rows):
        for t in (r.get("title"), r.get("subtitle", "")):
            hits = free(by_name.get(norm(t), []))
            if len(hits) > 1:
                ranked = sorted(hits, key=lambda h: -dep_score(r, h[1]))
                hits = ranked[:1] if dep_score(r, ranked[0][1]) > dep_score(r, ranked[1][1]) else []
            if len(hits) == 1:
                out[i] = (hits[0], "title")
                taken.add(hits[0][0])
                break
    # pass 2: conditional variants by dependency
    for i, r in enumerate(rows):
        if i in out:
            continue
        cands = [(k, p) for k, p in props if k not in taken]
        if r.get("type") == "geo":
            locs = [h for h in cands if "location" in h[1]]
            primary = "primary" in (r.get("map_discovery") or "").lower()
            locs.sort(key=lambda h: (h[1].get("location") == "primary") != primary)
            if len(locs) == 1 or (locs and primary):
                out[i] = (locs[0], "geo")
                taken.add(locs[0][0])
                continue
        # dependency first, title similarity breaks ties between variants on the same value
        target = norm(r.get("title"))
        scored = sorted(((dep_score(r, p), option_overlap(r, p), similarity(target, k, p), (k, p)) for k, p in cands),
                        key=lambda x: (-x[0], -x[1], -x[2]))
        if scored and scored[0][0] > 0 and (
                len(scored) == 1 or scored[0][0] > scored[1][0]
                or scored[0][1] - scored[1][1] >= 0.2 or scored[0][2] - scored[1][2] >= 0.05):
            out[i] = (scored[0][3], "dependency")
            taken.add(scored[0][3][0])
    # pass 3: fuzzy, only with a clear winner
    for i, r in enumerate(rows):
        if i in out:
            continue
        target = norm(r.get("title"))
        scored = sorted(((similarity(target, k, p), (k, p)) for k, p in props if k not in taken), key=lambda x: -x[0])
        # a clear winner only: good enough on its own and well ahead of the runner-up
        if scored and scored[0][0] >= 0.65 and (len(scored) == 1 or scored[0][0] - scored[1][0] >= 0.15):
            out[i] = (scored[0][1], "fuzzy")
            taken.add(scored[0][1][0])
    return out


def closest(row, props, taken):
    """Best near-match for a NEW row, as a hint only (never auto-paired)."""
    target = norm(row.get("title"))
    best = max(((difflib.SequenceMatcher(None, target, norm(p.get("title", k))).ratio(), k, p)
                for k, p in props if k not in taken), default=None, key=lambda x: x[0])
    return best if best and best[0] >= 0.5 else None
