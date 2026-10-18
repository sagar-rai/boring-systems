#!/usr/bin/env python3
"""
Usage:
    python3 excalidraw2mermaid.py [--no-merge] board.excalidraw > board.md
    pbpaste | python3 excalidraw2mermaid.py -
"""
import json
import math
import re
import sys

SNAP = 40
LABEL_DIST = 60
LIFELINE_SNAP = 30
TITLE_DIST = 400
SHAPES = ("rectangle", "diamond", "ellipse")


def bbox(e):
    if e.get("points"):
        xs = [e["x"] + p[0] for p in e["points"]]
        ys = [e["y"] + p[1] for p in e["points"]]
        return (min(xs), min(ys), max(xs), max(ys))
    return (e["x"], e["y"], e["x"] + e["width"], e["y"] + e["height"])


def center(b):
    return ((b[0] + b[2]) / 2, (b[1] + b[3]) / 2)


def inside(pt, b, pad=0):
    return b[0] - pad <= pt[0] <= b[2] + pad and b[1] - pad <= pt[1] <= b[3] + pad


def contains(outer, inner):
    return outer[0] <= inner[0] and outer[1] <= inner[1] and outer[2] >= inner[2] and outer[3] >= inner[3]


def pt_rect(p, b):
    dx = max(b[0] - p[0], 0, p[0] - b[2])
    dy = max(b[1] - p[1], 0, p[1] - b[3])
    return math.hypot(dx, dy)


def rect_rect(a, b):
    dx = max(a[0] - b[2], b[0] - a[2], 0)
    dy = max(a[1] - b[3], b[1] - a[3], 0)
    return math.hypot(dx, dy)


def pt_seg(p, a, b):
    ax, ay = a
    bx, by = b
    dx, dy = bx - ax, by - ay
    if dx == dy == 0:
        return math.hypot(p[0] - ax, p[1] - ay)
    t = max(0, min(1, ((p[0] - ax) * dx + (p[1] - ay) * dy) / (dx * dx + dy * dy)))
    return math.hypot(p[0] - (ax + t * dx), p[1] - (ay + t * dy))


def segs_cross(p1, p2, p3, p4):
    def orient(a, b, c):
        return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])
    d1, d2 = orient(p3, p4, p1), orient(p3, p4, p2)
    d3, d4 = orient(p1, p2, p3), orient(p1, p2, p4)
    return (d1 * d2 < 0) and (d3 * d4 < 0)


def seg_rect(a, b, r):
    if inside(a, r) or inside(b, r):
        return 0.0
    corners = [(r[0], r[1]), (r[2], r[1]), (r[2], r[3]), (r[0], r[3])]
    for i in range(4):
        if segs_cross(a, b, corners[i], corners[(i + 1) % 4]):
            return 0.0
    return min([pt_rect(a, r), pt_rect(b, r)] + [pt_seg(c, a, b) for c in corners])


def polyline(e):
    return [(e["x"] + p[0], e["y"] + p[1]) for p in e.get("points") or [[0, 0], [e["width"], e["height"]]]]


def poly_rect(e, r):
    pts = polyline(e)
    return min(seg_rect(pts[i], pts[i + 1], r) for i in range(len(pts) - 1))


def clean(t):
    return re.sub(r"\s+", " ", (t or "").strip())


def is_short(t, max_lines=2, max_len=60):
    t = (t or "").strip()
    return 0 < len(t) <= max_len and t.count("\n") < max_lines


def mm_label(t):
    t = (t or "").strip()
    for ch, code in (('"', "#quot;"), ("`", "#96;"), ("<", "#60;"), (">", "#62;")):
        t = t.replace(ch, code)
    return "<br/>".join(re.sub(r"\s+", " ", ln).strip() for ln in t.split("\n") if ln.strip())


def seq_text(t):
    t = mm_label(t).replace(";", ",").replace("#quot;", "'")
    return t or "(unlabeled)"


def load(path):
    raw = sys.stdin.read() if path == "-" else open(path, encoding="utf-8").read()
    data = json.loads(raw)
    if isinstance(data, list):
        els = data
    else:
        els = data.get("elements", [])
    return [e for e in els if not e.get("isDeleted")]


POINTING_HEADS = {"arrow", "triangle", "triangle_outline"}


def orient(a, s, t):
    start = a.get("startArrowhead") in POINTING_HEADS
    end = a.get("endArrowhead", "arrow") in POINTING_HEADS
    if start and end:
        return s, t, "both"
    if start:
        return t, s, "one"
    if end:
        return s, t, "one"
    return s, t, "none"


OPS = {
    ("one", False): "-->", ("one", True): "-.->",
    ("both", False): "<-->", ("both", True): "<-.->",
    ("none", False): "---", ("none", True): "-.-",
}


SEQ_OPS = {
    ("one", False): "->>", ("one", True): "-->>",
    ("both", False): "<<->>", ("both", True): "<<-->>",
    ("none", False): "->", ("none", True): "-->",
}


SKIPPED_TYPES = {"freedraw": "freehand drawing", "image": "image", "embeddable": "embedded page",
                 "iframe": "embedded page"}
RESERVED = {"end", "graph", "flowchart", "subgraph", "style", "linkstyle", "classdef", "class", "click",
            "call", "href", "default", "direction", "tb", "td", "bt", "rl", "lr"}


def convert(els, merge_bidirectional=True):
    els = [dict(e) for e in els]
    for e in els:
        if e["type"] == "text":
            e["text"] = e.get("originalText") or e.get("text", "")
    for f in [e for e in els if e["type"] in ("frame", "magicframe") and e.get("name")]:
        els.append({"id": f"frame:{f['id']}", "type": "text", "x": f["x"], "y": f["y"] - 35,
                    "width": f["width"], "height": 25, "text": f["name"]})
    skipped = {}
    for e in els:
        if e["type"] in SKIPPED_TYPES:
            skipped[SKIPPED_TYPES[e["type"]]] = skipped.get(SKIPPED_TYPES[e["type"]], 0) + 1
    by_id = {e["id"]: e for e in els}
    texts = [e for e in els if e["type"] == "text"]
    shapes = [e for e in els if e["type"] in SHAPES]
    arrows = [e for e in els if e["type"] == "arrow"]
    lines = [e for e in els if e["type"] == "line"]
    B = {e["id"]: bbox(e) for e in els}
    used = set()
    label = {}

    for t in texts:
        c = t.get("containerId")
        if c and c in by_id:
            label[c] = t.get("text", "")
            used.add(t["id"])

    groups = []
    for s in shapes:
        if s["type"] == "rectangle" and s["id"] not in label:
            members = [o for o in shapes if o is not s and contains(B[s["id"]], B[o["id"]])]
            if members:
                groups.append((s, members))
    group_ids = {g["id"] for g, _ in groups}
    nodes = [s for s in shapes if s["id"] not in group_ids]

    for t in texts:
        if t["id"] in used:
            continue
        c = center(B[t["id"]])
        hits = [s for s in nodes if s["id"] not in label and inside(c, B[s["id"]])]
        if hits:
            s = min(hits, key=lambda s: (B[s["id"]][2] - B[s["id"]][0]) * (B[s["id"]][3] - B[s["id"]][1]))
            label[s["id"]] = t.get("text", "")
            used.add(t["id"])

    def free_texts():
        return [t for t in texts if t["id"] not in used]

    lifelines = []
    for ln in lines:
        b = B[ln["id"]]
        w, h = b[2] - b[0], b[3] - b[1]
        if h < 100 or w > 0.15 * h:
            continue
        lx = (b[0] + b[2]) / 2
        cands = [t for t in free_texts() if is_short(t.get("text"), 1)
                 and 0 <= b[1] - B[t["id"]][3] <= 80 and B[t["id"]][0] - 80 <= lx <= B[t["id"]][2] + 80]
        if cands:
            head = min(cands, key=lambda t: b[1] - B[t["id"]][3])
            used.add(head["id"])
            lifelines.append({"id": ln["id"], "x": lx, "y1": b[1], "y2": b[3], "name": clean(head["text"]),
                              "bbox": (min(b[0], B[head["id"]][0]), B[head["id"]][1], max(b[2], B[head["id"]][2]), b[3])})

    def lifeline_at(p):
        best = None
        for L in lifelines:
            d = abs(p[0] - L["x"])
            if d <= LIFELINE_SNAP and L["y1"] - 10 <= p[1] <= L["y2"] + 10 and (best is None or d < best[0]):
                best = (d, L)
        return best[1] if best else None

    messages = []
    def free_text_at(binding):
        t = by_id.get((binding or {}).get("elementId"))
        return t if t and t["type"] == "text" and not t.get("containerId") and t["id"] not in used else None

    def node_at(binding, pt):
        tgt = by_id.get((binding or {}).get("elementId"))
        if tgt and tgt["type"] in SHAPES:
            return tgt["id"]
        near = [(pt_rect(pt, B[n["id"]]), n["id"]) for n in nodes]
        near = [x for x in near if x[0] <= SNAP]
        return min(near)[1] if near else None

    pointer_arrows = set()
    for a in arrows:
        pts = polyline(a)
        for text_end, node_end, pt in ((a.get("endBinding"), a.get("startBinding"), pts[0]),
                                       (a.get("startBinding"), a.get("endBinding"), pts[-1])):
            note = free_text_at(text_end)
            node = node_at(node_end, pt) if note else None
            if note and node:
                note["text"] = f"[{clean(label.get(node, ''))}] {note['text']}"
                pointer_arrows.add(a["id"])
                break
    arrows = [a for a in arrows if a["id"] not in pointer_arrows]

    flow_arrows = []
    for a in arrows:
        pts = polyline(a)
        s, t = lifeline_at(pts[0]), lifeline_at(pts[-1])
        if s and t and s is not t and not a.get("startBinding") and not a.get("endBinding"):
            messages.append((a, s, t))
        else:
            flow_arrows.append(a)

    group_title = {}
    for g, _ in groups:
        b = B[g["id"]]
        cands = [t for t in free_texts() if is_short(t.get("text"), 1)
                 and 0 <= b[1] - B[t["id"]][3] <= 80 and B[t["id"]][2] >= b[0] and B[t["id"]][0] <= b[2]]
        if cands:
            t = min(cands, key=lambda t: b[1] - B[t["id"]][3])
            group_title[g["id"]] = t.get("text", "")
            used.add(t["id"])

    pairs = []
    for a in arrows:
        if a["id"] in label:
            continue
        for t in free_texts():
            if not is_short(t.get("text")):
                continue
            d = poly_rect(a, B[t["id"]])
            if d <= LABEL_DIST:
                pairs.append((d, a["id"], t["id"]))
    taken_a = set()
    for d, aid, tid in sorted(pairs):
        if aid in taken_a or tid in used:
            continue
        label[aid] = by_id[tid].get("text", "")
        taken_a.add(aid)
        used.add(tid)

    endpoint_targets = nodes + [g for g, _ in groups]

    def resolve(binding, pt):
        if binding and binding.get("elementId") in by_id:
            tgt = by_id[binding["elementId"]]
            if tgt["type"] in SHAPES:
                return tgt["id"]
        best = None
        for s in endpoint_targets:
            d = pt_rect(pt, B[s["id"]])
            if d <= SNAP and (best is None or d < best[0]):
                best = (d, s["id"])
        return best[1] if best else None

    edges, dangling = [], []
    for a in flow_arrows:
        pts = polyline(a)
        s = resolve(a.get("startBinding"), pts[0])
        t = resolve(a.get("endBinding"), pts[-1])
        if s and t and s != t:
            edges.append((s, t, a))
        else:
            dangling.append((s, t, a))

    parent = {n["id"]: n["id"] for n in endpoint_targets}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a, b):
        parent[find(a)] = find(b)

    for s, t, _ in edges:
        union(s, t)
    for g, members in groups:
        for m in members:
            union(g["id"], m["id"])

    comps = {}
    for n in endpoint_targets:
        comps.setdefault(find(n["id"]), []).append(n["id"])

    connected = {x for s, t, _ in edges + dangling for x in (s, t) if x}
    for root, ids in list(comps.items()):
        if len(ids) == 1 and ids[0] not in connected and ids[0] not in group_ids:
            del comps[root]
            if label.get(ids[0], "").strip():
                box = {"id": f"box:{ids[0]}", "type": "text", "text": label[ids[0]]}
                B[box["id"]] = B[ids[0]]
                by_id[box["id"]] = box
                texts.append(box)

    diagrams = []
    for root, ids in comps.items():
        bx = [B[i] for i in ids]
        diagrams.append({"kind": "flow", "ids": set(ids),
                         "bbox": (min(b[0] for b in bx), min(b[1] for b in bx), max(b[2] for b in bx), max(b[3] for b in bx))})

    lifelines.sort(key=lambda L: L["x"])
    seq_groups = []
    for L in lifelines:
        for g in seq_groups:
            if any(not (L["y2"] < o["y1"] or L["y1"] > o["y2"]) for o in g):
                g.append(L)
                break
        else:
            seq_groups.append([L])
    for g in seq_groups:
        ids = {L["id"] for L in g}
        bx = [L["bbox"] for L in g]
        diagrams.append({"kind": "seq", "lifelines": g,
                         "msgs": [m for m in messages if m[1]["id"] in ids],
                         "bbox": (min(b[0] for b in bx), min(b[1] for b in bx), max(b[2] for b in bx), max(b[3] for b in bx))})

    for d in sorted(diagrams, key=lambda d: d["bbox"][1]):
        b = d["bbox"]
        cands = [t for t in free_texts() if is_short(t.get("text"), 1)
                 and -10 <= b[1] - B[t["id"]][3] <= TITLE_DIST
                 and B[t["id"]][2] >= b[0] - 200 and B[t["id"]][0] <= b[2] + 200]
        if cands:
            t = min(cands, key=lambda t: b[1] - B[t["id"]][3])
            d["title"] = clean(t["text"])
            used.add(t["id"])

    frames = [B[e["id"]] for e in els if e["type"] in ("frame", "magicframe")]

    def frame_of(b):
        c = center(b)
        hits = [f for f in frames if inside(c, f)]
        return min(hits, key=lambda f: (f[2] - f[0]) * (f[3] - f[1])) if hits else None

    loose = []
    for t in free_texts():
        if not diagrams:
            loose.append(t)
            continue
        f = frame_of(B[t["id"]])
        same = [d for d in diagrams if f and frame_of(d["bbox"]) == f]
        d = min(same or diagrams, key=lambda d: rect_rect(d["bbox"], B[t["id"]]))
        if rect_rect(d["bbox"], B[t["id"]]) <= 1500:
            d.setdefault("notes", []).append(t)
        else:
            loose.append(t)

    diagrams = [d for d in diagrams if d["kind"] == "seq" or len(d["ids"]) > 1 or d.get("notes") or d.get("title")]
    diagrams.sort(key=lambda d: d["bbox"][0])
    columns = []
    for d in diagrams:
        if columns and d["bbox"][0] <= columns[-1]["x2"]:
            columns[-1]["items"].append(d)
            columns[-1]["x2"] = max(columns[-1]["x2"], d["bbox"][2])
        else:
            columns.append({"x2": d["bbox"][2], "items": [d]})
    ordered = [d for c in columns for d in sorted(c["items"], key=lambda d: d["bbox"][1])]

    flow_edges = []
    for s, t, a in edges:
        f, to, direction = orient(a, s, t)
        flow_edges.append({"s": f, "t": to, "dir": direction,
                           "dashed": a.get("strokeStyle") in ("dashed", "dotted"),
                           "label": mm_label(label.get(a["id"], ""))})

    if merge_bidirectional:
        merged, consumed = [], set()
        for i, e in enumerate(flow_edges):
            if i in consumed:
                continue
            if e["dir"] == "one":
                j = next((j for j, f in enumerate(flow_edges)
                          if j > i and j not in consumed and f["dir"] == "one" and f["dashed"] == e["dashed"]
                          and f["s"] == e["t"] and f["t"] == e["s"]), None)
                if j is not None:
                    consumed.add(j)
                    back = flow_edges[j]["label"]
                    if e["label"] or back:
                        parts = ([f"→ {e['label']}"] if e["label"] else []) + ([f"← {back}"] if back else [])
                        lab = "<br/>".join(parts)
                    else:
                        lab = ""
                    merged.append({**e, "dir": "both", "label": lab})
                    continue
            merged.append(e)
        flow_edges = merged

    slugs = {}

    def slug(eid):
        if eid in slugs:
            return slugs[eid]
        base = clean(label.get(eid) or group_title.get(eid) or by_id[eid]["type"])
        words = re.sub(r"[^a-zA-Z0-9]+", " ", base).lower().split()[:4]
        s = "_".join(words)[:32].strip("_") or "node"
        if s[0].isdigit():
            s = "n_" + s
        if s in RESERVED:
            s += "_node"
        name, i = s, 2
        while name in slugs.values():
            name, i = f"{s}_{i}", i + 1
        slugs[eid] = name
        return name

    def node_decl(eid):
        e = by_id[eid]
        text = mm_label(label.get(eid, "")) or f"(unlabeled {e['type']})"
        sid = slug(eid)
        if e["type"] == "diamond":
            return f'{sid}{{"{text}"}}'
        if e["type"] == "ellipse":
            if re.search(r"\b(db|database|store)\b", label.get(eid, ""), re.I):
                return f'{sid}[("{text}")]'
            return f'{sid}(("{text}"))'
        return f'{sid}["{text}"]'

    out = ["<!-- Generated by excalidraw2mermaid.py.",
           "     Solid arrow = --> , dashed arrow = -.-> , two-way = <--> / <-.-> , no arrowhead = --- / -.- .",
           "     On a two-way edge 'A <--> B', a label starting with → describes A to B, and ← describes B to A.",
           "     A note starting with [Name] was attached by an arrow to the component called Name. -->",
           ""]
    if loose:
        out.append("## Text on the board, away from any diagram")
        for t in sorted(loose, key=lambda t: (B[t["id"]][1], B[t["id"]][0])):
            out.append("")
            out.append("\n".join("> " + ln for ln in t.get("text", "").strip().split("\n")))
        out.append("")
    for n, d in enumerate(ordered, 1):
        out.append(f"## {d.get('title') or f'Diagram {n}'}")
        out.append("")
        out.append("```mermaid")
        if d["kind"] == "seq":
            out.append("sequenceDiagram")
            pid = {}
            for i, L in enumerate(d["lifelines"], 1):
                pid[L["id"]] = f"p{i}"
                out.append(f"    participant p{i} as {seq_text(L['name'])}")
            for a, s, t in sorted(d["msgs"], key=lambda m: center(B[m[0]["id"]])[1]):
                f, to, direction = orient(a, s, t)
                dashed = a.get("strokeStyle") in ("dashed", "dotted")
                op = SEQ_OPS[(direction, dashed)]
                out.append(f"    {pid[f['id']]}{op}{pid[to['id']]}: {seq_text(label.get(a['id']))}")
        else:
            out.append("flowchart LR")
            in_group = {}
            for g, members in groups:
                if g["id"] in d["ids"]:
                    for m in members:
                        in_group[m["id"]] = g["id"]
            for eid in sorted(d["ids"], key=lambda i: (B[i][0], B[i][1])):
                if eid in group_ids or eid in in_group:
                    continue
                out.append(f"    {node_decl(eid)}")
            for g, members in groups:
                if g["id"] not in d["ids"]:
                    continue
                title = mm_label(group_title.get(g["id"], "")) or "group"
                out.append(f'    subgraph {slug(g["id"])}["{title}"]')
                for m in sorted(members, key=lambda m: (B[m["id"]][0], B[m["id"]][1])):
                    out.append(f"        {node_decl(m['id'])}")
                out.append("    end")
            for e in flow_edges:
                if e["s"] not in d["ids"]:
                    continue
                op = OPS[(e["dir"], e["dashed"])]
                lab = e["label"]
                out.append(f'    {slug(e["s"])} {op}|"{lab}"| {slug(e["t"])}' if lab
                           else f'    {slug(e["s"])} {op} {slug(e["t"])}')
        out.append("```")
        dang = [x for x in dangling if (x[0] and x[0] in d.get("ids", ())) or (x[1] and x[1] in d.get("ids", ()))]
        if dang:
            out.append("")
            out.append("Arrows with one loose end:")
            for s, t, a in dang:
                f, to, direction = orient(a, s, t)
                arrow = {"one": "->", "both": "<->", "none": "--"}[direction]
                lab = clean(label.get(a["id"], ""))
                name = lambda x: clean(label.get(x, "?")) if x else "(nothing)"
                out.append(f"- {name(f)} {arrow} {name(to)}" + (f' ("{lab}")' if lab else ""))
        if d.get("notes"):
            out.append("")
            out.append("Notes on this diagram:")
            for t in sorted(d["notes"], key=lambda t: (B[t["id"]][1], B[t["id"]][0])):
                body = t.get("text", "").strip()
                out.append("")
                out.append("\n".join("> " + ln for ln in body.split("\n")))
        out.append("")
    if skipped:
        out.append("")
        out.append("Not converted: " + ", ".join(f"{n} {k}{'s' if n > 1 else ''}" for k, n in skipped.items())
                   + ". Describe them in text if they matter to the design.")
    return "\n".join(out).rstrip() + "\n"


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if a != "--no-merge"]
    if len(args) != 1:
        sys.exit("usage: excalidraw2mermaid.py [--no-merge] <board.excalidraw | ->")
    sys.stdout.write(convert(load(args[0]), merge_bidirectional="--no-merge" not in sys.argv))
