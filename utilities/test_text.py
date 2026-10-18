#!/usr/bin/env python3
import importlib.util
import os
import random
import re

here = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location("x2m", os.path.join(here, "excalidraw2mermaid.py"))
x2m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(x2m)

random.seed(7)
els = []
n = [0]


def nid():
    n[0] += 1
    return f"e{n[0]}"


def wrap(s, width=28):
    out, line = [], ""
    for w in s.split(" "):
        if len(line) + len(w) + 1 > width and line:
            out.append(line)
            line = w
        else:
            line = (line + " " + w).strip()
    out.append(line)
    return "\n".join(out)


def text(x, y, s, w=300, container=None, wrapped=False):
    t = {"id": nid(), "type": "text", "x": x, "y": y, "width": w, "height": 25 * (s.count("\n") + 1),
         "text": wrap(s) if wrapped else s, "originalText": s}
    if container:
        t["containerId"] = container
    els.append(t)
    return t


def shape(kind, x, y, w, h, label=None, wrapped=False):
    s = {"id": nid(), "type": kind, "x": x, "y": y, "width": w, "height": h, "strokeStyle": "solid"}
    els.append(s)
    if label:
        text(x + 5, y + 5, label, w - 10, container=s["id"], wrapped=wrapped)
    return s


def arrow(a, b, lab=None, dashed=False):
    ax, ay = a["x"] + a["width"], a["y"] + a["height"] / 2
    bx, by = b["x"], b["y"] + b["height"] / 2
    ar = {"id": nid(), "type": "arrow", "x": ax, "y": ay, "width": abs(bx - ax), "height": abs(by - ay),
          "strokeStyle": "dashed" if dashed else "solid", "points": [[0, 0], [bx - ax, by - ay]],
          "startArrowhead": None, "endArrowhead": "arrow",
          "startBinding": {"elementId": a["id"]}, "endBinding": {"elementId": b["id"]}}
    els.append(ar)
    if lab:
        text(0, 0, lab, container=ar["id"])
    return ar


tricky = [
    'User "ID" only',
    "End",
    "graph",
    "`x` minutes",
    "latency < 300ms -> fail open?",
    "A | B; C: D #1 [x] {y} (z)",
    "då, über, 日本語, emoji 📦",
]

client = shape("diamond", 0, 0, 150, 150, "Client app")
gateway = shape("rectangle", 300, 40, 220, 80, "API gateway at the edge; decides allow or deny", wrapped=True)
srv = shape("rectangle", 650, 40, 260, 80,
            "Order service: owns the region's copy of open orders and the outbox of order events", wrapped=True)
db = shape("ellipse", 650, 300, 200, 120, "Local DB")
arrow(client, gateway, "request (user ID only)")
arrow(gateway, srv, "create or update, waits for answer under 300 ms")
arrow(srv, db)
for i, t in enumerate(tricky):
    s = shape("rectangle", 1000, i * 120, 220, 80, t)
    arrow(srv, s, t if i % 2 else None)

shape("rectangle", 0, 600, 600, 400,
      "Requirements: FR1 create or update an order. FR2 one open order per user. "
      "NFR1 response under 300 ms. NFR2 99.9% availability. Assumption: fail open on mobile.",
      wrapped=True)

note_box = shape("rectangle", 700, 600, 500, 300)
text(720, 620, "Open question:\nwhat happens when the remote server is unreachable\nand the user is unknown locally?")

long_lines = "\n".join(f"- point {i}: " + "word " * random.randint(3, 15) for i in range(40))
text(0, 1100, "Flow notes\n" + long_lines, w=900)

text(-50, -200, "Order service HLD", w=400)
els.append({"id": nid(), "type": "frame", "x": -100, "y": 2200, "width": 1200, "height": 800, "name": "Mobile flow"})
b1 = shape("rectangle", 0, 2400, 200, 80, "Mobile client")
b2 = shape("ellipse", 400, 2400, 200, 120, "Mobile local DB")
arrow(b1, b2, "read only while offline")
els.append({"id": nid(), "type": "freedraw", "x": 300, "y": 2600, "width": 100, "height": 50, "points": [[0, 0], [10, 10]]})
els.append({"id": nid(), "type": "image", "x": 600, "y": 2600, "width": 100, "height": 50})

for k in range(200):
    ox, oy = 3000 + (k % 10) * 900, (k // 10) * 700
    p = shape("rectangle", ox, oy, 200, 80, f"Service {k}")
    q = shape("ellipse", ox + 400, oy, 200, 120, f"Store {k}")
    arrow(p, q, f"writes {k}")
    text(ox, oy + 200, f"Note {k}: " + "lorem ipsum dolor sit amet " * random.randint(1, 8), w=600)

pointed = text(1300, -300, "Checks for an existing order before creating a new one", w=400)
arrow(srv, pointed)
text(-9000, -9000, "Problem statement, far from every diagram", w=500)
md = x2m.convert(els)


def norm(s):
    for code, ch in (("<br/>", " "), ("#quot;", '"'), ("#96;", "`"), ("#60;", "<"), ("#62;", ">")):
        s = s.replace(code, ch)
    s = re.sub(r"^> ?", "", s, flags=re.M)
    return re.sub(r"\s+", " ", s).strip().lower()


fails = 0


def check(name, ok):
    global fails
    fails += not ok
    print(f"{'PASS' if ok else 'FAIL'}  {name}")


out = norm(md)
missing = [e["originalText"] for e in els if e["type"] == "text" and norm(e["originalText"]) not in out]
check(f"no text lost ({len([e for e in els if e['type'] == 'text'])} text elements)", not missing)
for m in missing:
    print("      missing:", m[:70].replace("\n", " / "))
check("long labels keep the typed text, not Excalidraw's wrapping",
      "Order service: owns the region's copy of open orders and the outbox of order events" in md)
check("reserved word as a label gets a safe id", 'end_node["End"]' in md and 'graph_node["graph"]' in md)
check("backticks and angle brackets are escaped", "#96;x#96; minutes" in md and "latency #60; 300ms" in md)
check("ids stay short", max(len(m) for m in re.findall(r"^\s+(\w+)[\[{(]", md, flags=re.M)) <= 40)
check("text box with no arrows becomes a note", "> Requirements: FR1" in md)
check("free text typed inside an empty box is kept", "> Open question:" in md)
check("frame name becomes the diagram title", "## Mobile flow" in md)
check("skipped drawings are reported", "Not converted: 1 freehand drawing, 1 image." in md)
check("note pointed at by an arrow is tagged with its component",
      "> [Order service: owns the region's copy of open orders and the outbox of order events] Checks for an existing order" in md
      and "(nothing)" not in md)
check("text away from diagrams comes first", md.index("## Text on the board") < md.index("```mermaid"))
print(f"\n{'all passed' if not fails else f'{fails} FAILED'}")
raise SystemExit(1 if fails else 0)
