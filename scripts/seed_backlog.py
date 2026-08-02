#!/usr/bin/env python3
"""Seed the program backlog into GitHub issues, sub-issues and the project board.

Idempotent by issue title. Re-running after invitations are accepted backfills
assignees that could not be set on an earlier run.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
DRY = os.environ.get("DRY_RUN") == "1"
# ASSIGN_ONLY=1 skips project field and sub-issue work, which is already done.
ASSIGN_ONLY = os.environ.get("ASSIGN_ONLY") == "1"


def gh(*args: str, check: bool = True) -> str:
    proc = subprocess.run(
        ["gh", *args], capture_output=True, text=True, timeout=120
    )
    if proc.returncode != 0:
        if check:
            raise RuntimeError(f"gh {' '.join(args)}\n{proc.stderr.strip()}")
        return ""
    return proc.stdout.strip()


def gh_json(*args: str, check: bool = True):
    out = gh(*args, check=check)
    return json.loads(out) if out else None


# --------------------------------------------------------------------------- load

backlog = yaml.safe_load((ROOT / "program" / "backlog.yaml").read_text())
roster = yaml.safe_load((ROOT / "program" / "roster.yaml").read_text())

ORG = backlog["org"]
PROJECT_NUMBER = str(backlog["project_number"])
EPIC_REPO = backlog["epic_repo"]
WS_MEMBERS = roster["workstream_members"]

# --------------------------------------------------------- org membership + project

print("Resolving org members...")
members = {m["login"].lower() for m in gh_json("api", f"orgs/{ORG}/members", "--paginate")}
print(f"  {len(members)} accepted members (pending invitees cannot be assigned yet)")

print("Resolving project fields...")
project = gh_json("project", "view", PROJECT_NUMBER, "--owner", ORG, "--format", "json")
PROJECT_ID = project["id"]

fields_raw = gh_json(
    "project", "field-list", PROJECT_NUMBER, "--owner", ORG,
    "--format", "json", "-L", "50",
)["fields"]

FIELDS: dict[str, dict] = {}
for f in fields_raw:
    entry = {"id": f["id"], "options": {}}
    for opt in f.get("options", []) or []:
        entry["options"][opt["name"]] = opt["id"]
    FIELDS[f["name"]] = entry


def existing_issues(repo: str) -> dict[str, dict]:
    """title -> {number, id} for every issue in the repo (open or closed)."""
    rows = gh_json(
        "issue", "list", "--repo", f"{ORG}/{repo}", "--state", "all",
        "--limit", "1000", "--json", "number,title,id,assignees",
    ) or []
    return {
        r["title"]: {
            "number": r["number"],
            "id": r["id"],
            "assignees": {a["login"].lower() for a in (r.get("assignees") or [])},
        }
        for r in rows
    }


CACHE: dict[str, dict[str, dict]] = {}


def issue_index(repo: str) -> dict[str, dict]:
    if repo not in CACHE:
        CACHE[repo] = existing_issues(repo)
    return CACHE[repo]


# --------------------------------------------------------------------------- create

def assignees_for(epic: dict) -> tuple[list[str], list[str]]:
    wanted = epic.get("override_assignees") or WS_MEMBERS.get(epic["workstream"], [])
    can = [u for u in wanted if u.lower() in members]
    cannot = [u for u in wanted if u.lower() not in members]
    return can, cannot


def ensure_issue(repo: str, title: str, body: str, labels: list[str],
                 assignees: list[str]) -> dict:
    idx = issue_index(repo)
    if title in idx:
        rec = idx[title]
        # Backfill assignees. GitHub refuses to assign non-members, so people who
        # had not accepted their invitation on an earlier run were skipped. This
        # is what makes re-running after they join actually do something.
        missing = [a for a in assignees if a.lower() not in rec.get("assignees", set())]
        if missing and not DRY:
            gh("issue", "edit", str(rec["number"]), "--repo", f"{ORG}/{repo}",
               *[arg for a in missing for arg in ("--add-assignee", a)], check=False)
            print(f"    ~ {repo}#{rec['number']} +{','.join(missing)}")
        elif missing:
            print(f"    ~ [dry] {repo}#{rec['number']} would add {','.join(missing)}")
        else:
            print(f"    = {repo}#{rec['number']} {title[:56]}")
        return rec

    if DRY:
        print(f"    + [dry] {repo} {title[:64]}")
        return {"number": 0, "id": "dry"}

    args = ["issue", "create", "--repo", f"{ORG}/{repo}",
            "--title", title, "--body", body]
    for lb in labels:
        args += ["--label", lb]
    for a in assignees:
        args += ["--assignee", a]

    url = gh(*args).splitlines()[-1]
    number = int(url.rstrip("/").split("/")[-1])
    node = gh_json("issue", "view", str(number), "--repo", f"{ORG}/{repo}", "--json", "id")
    rec = {"number": number, "id": node["id"]}
    idx[title] = rec
    print(f"    + {repo}#{number} {title[:64]}")
    return rec


def link_sub_issue(parent_id: str, child_id: str) -> None:
    if ASSIGN_ONLY or DRY or parent_id == "dry" or child_id == "dry":
        return
    gh("api", "graphql",
       "-f", f"parent={parent_id}", "-f", f"child={child_id}",
       "-f", "query=mutation($parent:ID!,$child:ID!){"
             "addSubIssue(input:{issueId:$parent,subIssueId:$child}){"
             "subIssue{number}}}",
       check=False)


def add_to_project(issue_id: str, fields: dict[str, str]) -> None:
    if ASSIGN_ONLY or DRY or issue_id == "dry":
        return
    out = gh_json("api", "graphql",
                  "-f", f"project={PROJECT_ID}", "-f", f"content={issue_id}",
                  "-f", "query=mutation($project:ID!,$content:ID!){"
                        "addProjectV2ItemById(input:{projectId:$project,contentId:$content})"
                        "{item{id}}}",
                  check=False)
    if not out:
        return
    item_id = out["data"]["addProjectV2ItemById"]["item"]["id"]

    for fname, value in fields.items():
        meta = FIELDS.get(fname)
        if not meta:
            continue
        if meta["options"]:
            opt = meta["options"].get(str(value))
            if not opt:
                continue
            val = f'{{singleSelectOptionId:"{opt}"}}'
        else:
            val = f"{{number:{value}}}"
        gh("api", "graphql",
           "-f", f"project={PROJECT_ID}", "-f", f"item={item_id}",
           "-f", f"field={meta['id']}",
           "-f", "query=mutation($project:ID!,$item:ID!,$field:ID!){"
                 "updateProjectV2ItemFieldValue(input:{projectId:$project,itemId:$item,"
                 f"fieldId:$field,value:{val}}}){{projectV2Item{{id}}}}}}",
           check=False)


# --------------------------------------------------------------------------- run

created = skipped = 0
unassignable: set[str] = set()

for epic in backlog["epics"]:
    ws = epic["workstream"]
    can, cannot = assignees_for(epic)
    unassignable.update(cannot)

    owners_note = ""
    if cannot:
        owners_note = (
            "\n\n**Pending assignment** (org invitation not yet accepted): "
            + ", ".join(f"@{u}" for u in cannot)
            + "\n\nRe-run `scripts/seed-backlog.sh` once they join to assign automatically."
        )

    epic_body = (
        f"{epic['body']}\n\n"
        f"- **Workstream:** `{ws}`\n"
        f"- **Wave:** {epic['wave']}\n"
        f"- **Layer:** `{epic['layer']}`\n\n"
        f"Tasks are tracked as sub-issues in the repository where the work lands."
        f"{owners_note}"
    )

    print(f"\n[{epic['key']}] {epic['title']}")
    parent = ensure_issue(
        EPIC_REPO, epic["title"], epic_body,
        ["type:epic", f"ws:{ws}", f"pri:{epic['priority']}"], can,
    )
    add_to_project(parent["id"], {
        "Status": "Backlog", "Workstream": ws, "Layer": epic["layer"],
        "Priority": epic["priority"], "Wave": epic["wave"],
    })

    for task in epic["tasks"]:
        repo = task["repo"]
        body = (
            f"Part of epic **{epic['title']}**.\n\n"
            f"- **Workstream:** `{ws}`\n"
            f"- **Wave:** {epic['wave']}\n"
            f"- **Owners:** {', '.join('@' + u for u in (epic.get('override_assignees') or WS_MEMBERS[ws]))}\n\n"
            f"### Definition of done\n"
            f"- [ ] Change merged through a reviewed pull request\n"
            f"- [ ] Applied and verified in the cluster or account\n"
            f"- [ ] Documented in `ops-program` where it affects other workstreams\n"
        )
        child = ensure_issue(
            repo, task["title"], body,
            ["type:task", f"ws:{ws}", f"pri:{epic['priority']}", f"size:{task['size']}"],
            can,
        )
        link_sub_issue(parent["id"], child["id"])
        add_to_project(child["id"], {
            "Status": "Backlog", "Workstream": ws, "Layer": epic["layer"],
            "Priority": epic["priority"], "Size": task["size"], "Wave": epic["wave"],
        })

print("\n" + "=" * 60)
print(f"Epics: {len(backlog['epics'])}   "
      f"Tasks: {sum(len(e['tasks']) for e in backlog['epics'])}")
if unassignable:
    print(f"\nNot yet assignable ({len(unassignable)} pending org invitations):")
    print("  " + ", ".join(sorted(unassignable)))
    print("  Re-run this script after they accept to backfill assignees.")
