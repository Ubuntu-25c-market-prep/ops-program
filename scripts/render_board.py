#!/usr/bin/env python3
"""Render the live Platform Build project board as a self-contained HTML page."""
from __future__ import annotations

import json
import subprocess
import sys
from collections import Counter, defaultdict
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
ORG = "Ubuntu-25c-market-prep"
OUT = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "board.html"

backlog = yaml.safe_load((ROOT / "program" / "backlog.yaml").read_text())
roster = yaml.safe_load((ROOT / "program" / "roster.yaml").read_text())
WS_MEMBERS = roster["workstream_members"]
NAME_OF = {p["github"]: p["name"] for p in roster["people"]}

items = json.loads(subprocess.run(
    ["gh", "project", "item-list", "1", "--owner", ORG, "--format", "json", "-L", "600"],
    capture_output=True, text=True, check=True).stdout)["items"]

by_title = {i["title"]: i for i in items}
epics_live = [i for i in items if "type:epic" in (i.get("labels") or [])]
tasks_live = [i for i in items if "type:task" in (i.get("labels") or [])]

WAVE_LABEL = {
    0: "Bootstrap", 1: "Foundations", 2: "Cluster", 3: "Platform primitives",
    4: "Mesh and scaling", 5: "Observability", 6: "Delivery and ops", 7: "Advanced",
}

waves: dict[int, list[dict]] = defaultdict(list)
repo_counts: Counter = Counter()
ws_counts: Counter = Counter()
person_counts: Counter = Counter()

for epic in backlog["epics"]:
    live = by_title.get(epic["title"], {})
    content = live.get("content", {}) or {}
    owners = epic.get("override_assignees") or WS_MEMBERS[epic["workstream"]]
    task_repos = Counter(t["repo"] for t in epic["tasks"])
    for t in epic["tasks"]:
        repo_counts[t["repo"]] += 1
        ws_counts[epic["workstream"]] += 1
    for o in owners:
        person_counts[o] += len(epic["tasks"])
    waves[epic["wave"]].append({
        "title": epic["title"], "key": epic["key"], "ws": epic["workstream"],
        "layer": epic["layer"], "pri": epic["priority"], "tasks": len(epic["tasks"]),
        "owners": owners, "repos": task_repos.most_common(),
        "url": content.get("url", ""), "number": content.get("number", ""),
        "assigned": live.get("assignees") or [],
        "body": epic["body"].strip().split("\n")[0],
    })

total_issues = len(epics_live) + len(tasks_live)
planned = len(backlog["epics"]) + sum(len(e["tasks"]) for e in backlog["epics"])
assigned = sum(1 for i in items if i.get("assignees"))

LAYER_TONE = {"infra": "l-infra", "platform": "l-platform",
              "gitops": "l-gitops", "apps": "l-apps", "ops": "l-ops"}


def esc(s: str) -> str:
    return (str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def initials(login: str) -> str:
    name = NAME_OF.get(login, login)
    parts = [p for p in name.replace("-", " ").split() if p]
    return (parts[0][0] + (parts[1][0] if len(parts) > 1 else "")).upper()


# ------------------------------------------------------------------- markup

wave_html = []
for w in sorted(waves):
    cards = []
    for e in sorted(waves[w], key=lambda x: (x["pri"], x["ws"])):
        owner_chips = "".join(
            f'<span class="who{"" if o in e["assigned"] else " who-pending"}" '
            f'title="{esc(NAME_OF.get(o, o))} ({esc(o)})'
            f'{"" if o in e["assigned"] else " — invitation pending"}">{esc(initials(o))}</span>'
            for o in e["owners"])
        repo_chips = "".join(
            f'<span class="repo"><span class="repo-n">{n}</span>{esc(r)}</span>'
            for r, n in e["repos"])
        link = f' href="{esc(e["url"])}"' if e["url"] else ""
        num = f'<span class="num">#{e["number"]}</span>' if e["number"] else ""
        cards.append(f"""
        <a class="card {LAYER_TONE[e['layer']]}"{link}>
          <div class="card-top">
            <span class="ws">{esc(e['ws'])}</span>
            <span class="pri p-{e['pri']}">{e['pri']}</span>
          </div>
          <h3>{esc(e['title'])}{num}</h3>
          <p>{esc(e['body'])}</p>
          <div class="repos">{repo_chips}</div>
          <div class="card-foot">
            <span class="tasks"><b>{e['tasks']}</b> sub-issues</span>
            <span class="whos">{owner_chips}</span>
          </div>
        </a>""")
    wave_html.append(f"""
    <section class="wave">
      <div class="wave-head">
        <span class="wave-n">Wave {w}</span>
        <h2>{esc(WAVE_LABEL[w])}</h2>
        <span class="wave-meta">{len(waves[w])} epic{'s' if len(waves[w]) != 1 else ''}
          · {sum(c['tasks'] for c in waves[w])} tasks</span>
      </div>
      <div class="cards">{''.join(cards)}</div>
    </section>""")

ws_rows = "".join(
    f'<tr><td class="mono">{esc(ws)}</td><td class="n">{n}</td>'
    f'<td class="bar"><i style="--w:{n / max(ws_counts.values()) * 100:.0f}%"></i></td></tr>'
    for ws, n in ws_counts.most_common())

repo_rows = "".join(
    f'<tr><td class="mono">{esc(r)}</td><td class="n">{n}</td>'
    f'<td class="bar"><i style="--w:{n / max(repo_counts.values()) * 100:.0f}%"></i></td></tr>'
    for r, n in repo_counts.most_common())

people_rows = "".join(
    f'<tr><td>{esc(NAME_OF.get(p, p))}</td><td class="mono dim">{esc(p)}</td>'
    f'<td class="n">{len(WS_MEMBERS and [w for w, m in WS_MEMBERS.items() if p in m])}</td>'
    f'<td class="n">{n}</td></tr>'
    for p, n in sorted(person_counts.items(), key=lambda kv: -kv[1]))

HTML = f"""<title>Platform Build — Program Board</title>
<style>
:root {{
  --ground:#F4F6F7; --surface:#FFFFFF; --surface-2:#EDF1F2;
  --ink:#101619; --ink-2:#4A5A60; --ink-3:#7C8D94;
  --line:#DCE3E5; --line-2:#C6D1D4;
  --accent:#17636B; --accent-soft:#DCEBEC;
  --p1:#A3271F; --p2:#A8613A; --p3:#7C8D94;
  --w0:#CFE0E2; --w7:#0E4B52;
}}
@media (prefers-color-scheme: dark) {{
  :root {{
    --ground:#0E1315; --surface:#161D20; --surface-2:#1D262A;
    --ink:#E6EDEF; --ink-2:#A3B3B8; --ink-3:#71858B;
    --line:#263236; --line-2:#334348;
    --accent:#5FB3BC; --accent-soft:#17383C;
    --p1:#E0796F; --p2:#D79A6E; --p3:#71858B;
    --w0:#22383C; --w7:#7FC9D1;
  }}
}}
:root[data-theme="dark"] {{
  --ground:#0E1315; --surface:#161D20; --surface-2:#1D262A;
  --ink:#E6EDEF; --ink-2:#A3B3B8; --ink-3:#71858B;
  --line:#263236; --line-2:#334348;
  --accent:#5FB3BC; --accent-soft:#17383C;
  --p1:#E0796F; --p2:#D79A6E; --p3:#71858B;
  --w0:#22383C; --w7:#7FC9D1;
}}
:root[data-theme="light"] {{
  --ground:#F4F6F7; --surface:#FFFFFF; --surface-2:#EDF1F2;
  --ink:#101619; --ink-2:#4A5A60; --ink-3:#7C8D94;
  --line:#DCE3E5; --line-2:#C6D1D4;
  --accent:#17636B; --accent-soft:#DCEBEC;
  --p1:#A3271F; --p2:#A8613A; --p3:#7C8D94;
  --w0:#CFE0E2; --w7:#0E4B52;
}}
* {{ box-sizing:border-box; }}
body {{
  margin:0; background:var(--ground); color:var(--ink);
  font-family:system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;
  font-size:15px; line-height:1.55; -webkit-font-smoothing:antialiased;
}}
.mono, .ws, .repo, .num, .wave-n, code {{
  font-family:ui-monospace,SFMono-Regular,"SF Mono",Menlo,Consolas,monospace;
}}
.wrap {{ max-width:1180px; margin:0 auto; padding:40px 24px 80px; }}

header {{ border-bottom:2px solid var(--ink); padding-bottom:22px; margin-bottom:6px; }}
.eyebrow {{
  font-family:ui-monospace,SFMono-Regular,Menlo,monospace; font-size:11px;
  letter-spacing:.14em; text-transform:uppercase; color:var(--accent); margin:0 0 10px;
}}
h1 {{ font-size:clamp(28px,4vw,42px); line-height:1.05; letter-spacing:-.025em;
     margin:0 0 8px; font-weight:680; text-wrap:balance; }}
.sub {{ color:var(--ink-2); margin:0; max-width:62ch; }}

.stats {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(132px,1fr));
          gap:1px; background:var(--line); border:1px solid var(--line);
          margin:26px 0 44px; }}
.stat {{ background:var(--surface); padding:16px 18px; }}
.stat b {{ display:block; font-size:26px; font-weight:660; letter-spacing:-.02em;
           font-variant-numeric:tabular-nums; line-height:1.1; }}
.stat span {{ font-size:11px; letter-spacing:.09em; text-transform:uppercase;
              color:var(--ink-3); }}

.wave {{ margin-bottom:38px; }}
.wave-head {{ display:flex; align-items:baseline; gap:14px; flex-wrap:wrap;
              padding-bottom:10px; margin-bottom:16px; border-bottom:1px solid var(--line-2); }}
.wave-n {{ font-size:11px; letter-spacing:.1em; text-transform:uppercase;
           color:var(--surface); background:var(--accent); padding:3px 8px; }}
.wave-head h2 {{ font-size:19px; font-weight:640; letter-spacing:-.015em; margin:0; }}
.wave-meta {{ margin-left:auto; font-size:12px; color:var(--ink-3);
              font-variant-numeric:tabular-nums; }}

.cards {{ display:grid; grid-template-columns:repeat(auto-fill,minmax(310px,1fr)); gap:14px; }}
.card {{ display:flex; flex-direction:column; gap:9px; background:var(--surface);
         border:1px solid var(--line); border-left:3px solid var(--layer,var(--accent));
         padding:15px 16px; text-decoration:none; color:inherit; transition:border-color .12s; }}
.card:hover {{ border-color:var(--line-2); border-left-color:var(--layer,var(--accent)); }}
.card:focus-visible {{ outline:2px solid var(--accent); outline-offset:2px; }}
.l-infra    {{ --layer:#17636B; }}
.l-platform {{ --layer:#A8613A; }}
.l-gitops   {{ --layer:#4A6B8A; }}
.l-apps     {{ --layer:#6B7F4A; }}
.l-ops      {{ --layer:#7C8D94; }}
.card-top {{ display:flex; align-items:center; gap:8px; }}
.ws {{ font-size:11px; color:var(--accent); background:var(--accent-soft);
       padding:2px 7px; letter-spacing:.02em; }}
.pri {{ margin-left:auto; font-size:10px; font-weight:700; letter-spacing:.08em; }}
.p-P1 {{ color:var(--p1); }} .p-P2 {{ color:var(--p2); }} .p-P3 {{ color:var(--p3); }}
.card h3 {{ font-size:14.5px; font-weight:620; letter-spacing:-.01em; margin:0;
            line-height:1.35; text-wrap:balance; }}
.num {{ font-size:11px; color:var(--ink-3); font-weight:400; margin-left:6px; }}
.card p {{ font-size:12.5px; color:var(--ink-2); margin:0; line-height:1.5; }}
.repos {{ display:flex; flex-wrap:wrap; gap:5px; }}
.repo {{ font-size:10.5px; color:var(--ink-2); background:var(--surface-2);
         border:1px solid var(--line); padding:1px 6px; }}
.repo-n {{ color:var(--ink-3); margin-right:5px; font-variant-numeric:tabular-nums; }}
.card-foot {{ display:flex; align-items:center; gap:10px; margin-top:auto; padding-top:4px; }}
.tasks {{ font-size:11.5px; color:var(--ink-3); font-variant-numeric:tabular-nums; }}
.tasks b {{ color:var(--ink); font-weight:640; }}
.whos {{ margin-left:auto; display:flex; }}
.who {{ width:23px; height:23px; border-radius:50%; display:grid; place-items:center;
        font-size:9.5px; font-weight:680; letter-spacing:.02em;
        background:var(--accent); color:var(--surface);
        border:1.5px solid var(--surface); margin-left:-6px; }}
.who-pending {{ background:var(--surface-2); color:var(--ink-3);
                border:1.5px dashed var(--line-2); }}

.grids {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(300px,1fr));
          gap:28px; margin-top:52px; }}
.panel h2 {{ font-size:13px; letter-spacing:.09em; text-transform:uppercase;
             color:var(--ink-3); margin:0 0 12px; font-weight:640; }}
.scroll {{ overflow-x:auto; }}
table {{ width:100%; border-collapse:collapse; font-size:13px; }}
th, td {{ text-align:left; padding:6px 10px 6px 0; border-bottom:1px solid var(--line); }}
th {{ font-size:10.5px; letter-spacing:.08em; text-transform:uppercase;
      color:var(--ink-3); font-weight:620; }}
td.n {{ text-align:right; font-variant-numeric:tabular-nums; width:44px; }}
td.dim {{ color:var(--ink-3); font-size:11.5px; }}
td.bar {{ width:38%; }}
td.bar i {{ display:block; height:6px; width:var(--w); background:var(--accent); opacity:.55; }}

footer {{ margin-top:56px; padding-top:18px; border-top:1px solid var(--line);
          font-size:12px; color:var(--ink-3); display:flex; gap:18px; flex-wrap:wrap; }}
footer a {{ color:var(--accent); }}
@media (prefers-reduced-motion:reduce) {{ * {{ transition:none !important; }} }}
</style>

<div class="wrap">
<header>
  <p class="eyebrow">Ubuntu-25c-market-prep · greenfield AWS EKS platform</p>
  <h1>Platform Build</h1>
  <p class="sub">Sixteen people across fifteen workstreams, sequenced into eight waves.
     Epics live in <code>ops-program</code> and own their tasks as cross-repository
     sub-issues. Waves encode the dependency chain: the landing zone gates the cluster,
     the cluster gates Flux, Flux gates every add-on, Istio gates ZeroTrust.</p>
</header>

<div class="stats">
  <div class="stat"><b>{total_issues}</b><span>issues on board</span></div>
  <div class="stat"><b>{len(backlog['epics'])}</b><span>epics</span></div>
  <div class="stat"><b>15</b><span>workstreams</span></div>
  <div class="stat"><b>10</b><span>repositories</span></div>
  <div class="stat"><b>16</b><span>people</span></div>
  <div class="stat"><b>8</b><span>waves</span></div>
</div>

{''.join(wave_html)}

<div class="grids">
  <div class="panel">
    <h2>Tasks per workstream</h2>
    <div class="scroll"><table>
      <thead><tr><th>Workstream</th><th class="n">Tasks</th><th></th></tr></thead>
      <tbody>{ws_rows}</tbody>
    </table></div>
  </div>
  <div class="panel">
    <h2>Tasks per repository</h2>
    <div class="scroll"><table>
      <thead><tr><th>Repository</th><th class="n">Tasks</th><th></th></tr></thead>
      <tbody>{repo_rows}</tbody>
    </table></div>
  </div>
  <div class="panel">
    <h2>Load per person</h2>
    <div class="scroll"><table>
      <thead><tr><th>Person</th><th>GitHub</th><th class="n">WS</th><th class="n">Tasks</th></tr></thead>
      <tbody>{people_rows}</tbody>
    </table></div>
  </div>
</div>

<footer>
  <span>{assigned} of {total_issues} issues assigned — the rest await org invitation acceptance</span>
  <a href="https://github.com/orgs/{ORG}/projects/1">Open the board on GitHub</a>
</footer>
</div>
"""

OUT.write_text(HTML)
print(f"wrote {OUT}  ({total_issues} issues, {len(backlog['epics'])} epics)")
