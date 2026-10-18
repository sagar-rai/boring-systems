#!/usr/bin/env python3
import importlib.util
import os
import re
import sys

here = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location("x2m", os.path.join(here, "excalidraw2mermaid.py"))
x2m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(x2m)

_n = [0]


def nid():
    _n[0] += 1
    return f"id{_n[0]}"


def rect(label, x, y, w=120, h=60):
    r, t = nid(), nid()
    return [
        {"id": r, "type": "rectangle", "x": x, "y": y, "width": w, "height": h, "strokeStyle": "solid",
         "boundElements": [{"id": t, "type": "text"}]},
        {"id": t, "type": "text", "x": x + 10, "y": y + 20, "width": 50, "height": 20, "text": label, "containerId": r},
    ], r


def arrow(x1, y1, x2, y2, start=None, end="arrow", dashed=False, sb=None, eb=None):
    a = {"id": nid(), "type": "arrow", "x": x1, "y": y1, "width": abs(x2 - x1), "height": abs(y2 - y1),
         "strokeStyle": "dashed" if dashed else "solid", "points": [[0, 0], [x2 - x1, y2 - y1]],
         "startArrowhead": start, "endArrowhead": end}
    if sb:
        a["startBinding"] = {"elementId": sb}
    if eb:
        a["endBinding"] = {"elementId": eb}
    return a


def flow_edges(md):
    return [l.strip() for l in md.splitlines() if re.match(r"\s+\w+ (<?-[-.]+>?|---|-\.-)[ |]", l)]


def flow_case(name, start, end, reverse=False, bound=True, dashed=False, merge=True):
    a_els, A = rect("A", 0, 0)
    b_els, B = rect("B", 400, 0)
    if reverse:
        ar = arrow(400, 30, 120, 30, start, end, dashed, B if bound else None, A if bound else None)
    else:
        ar = arrow(120, 30, 400, 30, start, end, dashed, A if bound else None, B if bound else None)
    md = x2m.convert(a_els + b_els + [ar], merge_bidirectional=merge)
    return flow_edges(md)


def seq_case(start, end, reverse=False, dashed=False):
    els = []
    for name, x in (("Client", 0), ("Server", 300)):
        els.append({"id": nid(), "type": "line", "x": x, "y": 0, "width": 0, "height": 300, "strokeStyle": "solid",
                    "points": [[0, 0], [0, 300]]})
        els.append({"id": nid(), "type": "text", "x": x - 20, "y": -40, "width": 60, "height": 20, "text": name})
    els.append(arrow(300, 100, 0, 100, start, end, dashed) if reverse else arrow(0, 100, 300, 100, start, end, dashed))
    md = x2m.convert(els)
    return [l.strip() for l in md.splitlines() if re.match(r"\s+p\d", l)]


fails = 0


def check(name, got, want):
    global fails
    ok = got == want
    fails += not ok
    print(f"{'PASS' if ok else 'FAIL'}  {name}: {got}" + ("" if ok else f"   expected {want}"))


check("end head, drawn A->B", flow_case("", None, "arrow"), ["a --> b"])
check("end head, drawn B->A", flow_case("", None, "arrow", reverse=True), ["b --> a"])
check("end head, unbound A->B", flow_case("", None, "arrow", bound=False), ["a --> b"])
check("end head, unbound B->A", flow_case("", None, "arrow", reverse=True, bound=False), ["b --> a"])
check("start head only, drawn A->B", flow_case("", "arrow", None), ["b --> a"])
check("start head only, drawn B->A", flow_case("", "arrow", None, reverse=True), ["a --> b"])
check("triangle end head", flow_case("", None, "triangle"), ["a --> b"])
check("dot start + arrow end is one-way", flow_case("", "dot", "arrow"), ["a --> b"])
check("arrow start + bar end is one-way back", flow_case("", "arrow", "bar"), ["b --> a"])
check("both heads", flow_case("", "arrow", "arrow"), ["a <--> b"])
check("no heads", flow_case("", None, None), ["a --- b"])
check("markers only (bar/dot)", flow_case("", "bar", "dot"), ["a --- b"])
check("dashed end head", flow_case("", None, "arrow", dashed=True), ["a -.-> b"])
check("dashed start head", flow_case("", "arrow", None, dashed=True), ["b -.-> a"])
check("dashed both heads", flow_case("", "arrow", "arrow", dashed=True), ["a <-.-> b"])


def pair(first, second, merge=True):
    a_els, A = rect("A", 0, 0)
    b_els, B = rect("B", 400, 0)
    return flow_edges(x2m.convert(a_els + b_els + [first(A, B), second(A, B)], merge_bidirectional=merge))


fwd = lambda A, B: arrow(120, 20, 400, 20, None, "arrow", sb=A, eb=B)
back = lambda A, B: arrow(400, 40, 120, 40, None, "arrow", sb=B, eb=A)
back_via_start_head = lambda A, B: arrow(120, 40, 400, 40, "arrow", None, sb=A, eb=B)
fwd2 = lambda A, B: arrow(120, 40, 400, 40, None, "arrow", sb=A, eb=B)
back_dashed = lambda A, B: arrow(400, 40, 120, 40, None, "arrow", True, sb=B, eb=A)

check("A->B + B->A merge", pair(fwd, back), ["a <--> b"])
check("A->B + start-head arrow pointing at A merge", pair(fwd, back_via_start_head), ["a <--> b"])
check("A->B twice does not merge", pair(fwd, fwd2), ["a --> b", "a --> b"])
check("solid A->B + dashed B->A do not merge", pair(fwd, back_dashed), ["a --> b", "b -.-> a"])
check("--no-merge keeps both", pair(fwd, back, merge=False), ["a --> b", "b --> a"])


def labelled(arrow_el, text):
    t = {"id": nid(), "type": "text", "x": 0, "y": 0, "width": 10, "height": 10, "text": text,
         "containerId": arrow_el["id"]}
    return [arrow_el, t]


a_els, A = rect("A", 0, 0)
b_els, B = rect("B", 400, 0)
md = x2m.convert(a_els + b_els + labelled(back(A, B), "response") + labelled(fwd(A, B), "request"))
check("labelled pair keeps label directions", flow_edges(md), ['b <-->|"→ response<br/>← request"| a'])

check("seq end head L->R", seq_case(None, "arrow"), ["p1->>p2: (unlabeled)"])
check("seq end head R->L", seq_case(None, "arrow", reverse=True), ["p2->>p1: (unlabeled)"])
check("seq start head only L->R", seq_case("arrow", None), ["p2->>p1: (unlabeled)"])
check("seq both heads", seq_case("arrow", "arrow"), ["p1<<->>p2: (unlabeled)"])
check("seq no heads", seq_case(None, None), ["p1->p2: (unlabeled)"])
check("seq dashed reply R->L", seq_case(None, "arrow", reverse=True, dashed=True), ["p2-->>p1: (unlabeled)"])

print(f"\n{'all passed' if not fails else f'{fails} FAILED'}")
sys.exit(1 if fails else 0)
