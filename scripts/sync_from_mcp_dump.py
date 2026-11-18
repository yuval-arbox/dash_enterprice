#!/usr/bin/env python3
"""
Rebuilds index.html from Jira search results saved by the Atlassian MCP
connector, for when the dashboard is synced from a Claude session instead
of the scheduled GitHub Action (which needs JIRA_EMAIL / JIRA_API_TOKEN).

The grouping and rendering logic is the one in build_enterprise_tickets.py;
this script only swaps its two Jira fetch functions for files on disk.

Workflow (all files go in one dump directory):

1. Save every ECS issue with these fields, split over files named
   ecs_*.json (each file is one searchJiraIssuesUsingJql result,
   view "full"):
     summary, status, issuetype, customfield_10301, customfield_11074,
     assignee, duedate, fixVersions, resolutiondate, priority, created,
     updated, issuelinks

2. Run:  python3 scripts/sync_from_mcp_dump.py keys <dump_dir>
   It prints the RD/PM/DB keys linked to customer Epics, in JQL-ready
   batches of 100, and writes them to <dump_dir>/devkeys.json.

3. Save each batch's result (fields: created, updated, assignee, duedate,
   fixVersions, customfield_11074, resolutiondate) as dev_*.json.

4. Run:  python3 scripts/sync_from_mcp_dump.py build <dump_dir>
   It rewrites index.html and prints what changed against the previous
   version (new / dropped tickets, status and Due Date changes).
"""
import importlib.util
import json
import os
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEV_LINK_TYPE = "Polaris datapoint work item link"
DEV_PROJECT_KEYS = {"RD", "PM", "DB"}


def load_builder():
    path = os.path.join(REPO_ROOT, "scripts", "build_enterprise_tickets.py")
    spec = importlib.util.spec_from_file_location("build_enterprise_tickets", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def to_rest(node):
    """MCP results put custom fields under fields.customFields keyed by
    their label; the builder expects plain customfield_* keys."""
    fields = dict(node["fields"])
    for cf in (fields.pop("customFields", None) or {}).values():
        fields[cf["id"]] = cf["value"]
    return {"key": node["key"], "fields": fields}


def load_nodes(dump_dir, prefix):
    nodes = []
    for name in sorted(os.listdir(dump_dir)):
        if name.startswith(prefix) and name.endswith(".json"):
            with open(os.path.join(dump_dir, name), encoding="utf-8") as f:
                nodes += [to_rest(n) for n in json.load(f)["issues"]["nodes"]]
    return nodes


def linked_keys(ecs_nodes):
    keys = set()
    for it in ecs_nodes:
        if it["fields"]["issuetype"]["name"] != "Epic":
            continue
        for link in it["fields"].get("issuelinks") or []:
            if link.get("type", {}).get("name") != DEV_LINK_TYPE:
                continue
            other = link.get("inwardIssue") or link.get("outwardIssue")
            if other and other["key"].split("-")[0] in DEV_PROJECT_KEYS:
                keys.add(other["key"])
    return sorted(keys, key=lambda k: (k.split("-")[0], int(k.split("-")[1])))


def read_dataset(html_path):
    with open(html_path, encoding="utf-8") as f:
        for line in f:
            if line.startswith("const DATA = "):
                return json.loads(line[len("const DATA = "):].rstrip().rstrip(";"))
    return {"tickets": []}


def by_key(dataset):
    out = {}
    for t in dataset["tickets"]:
        out.setdefault(t["key"], dict(t, bizs=set()))["bizs"].add(t["business"])
    return out


def cmd_keys(dump_dir):
    ecs = load_nodes(dump_dir, "ecs_")
    keys = set(n["key"] for n in ecs)
    if len(keys) != len(ecs):
        sys.exit(f"Duplicate ECS issues across ecs_*.json files ({len(ecs)} rows, {len(keys)} keys)")
    dev = linked_keys(ecs)
    with open(os.path.join(dump_dir, "devkeys.json"), "w") as f:
        json.dump(dev, f)
    print(f"{len(ecs)} ECS issues, {len(dev)} linked RD/PM/DB issues")
    for i in range(0, len(dev), 100):
        print("key in ({})".format(", ".join(dev[i:i + 100])))


def cmd_build(dump_dir):
    b = load_builder()
    ecs = load_nodes(dump_dir, "ecs_")
    dev = {n["key"]: n for n in load_nodes(dump_dir, "dev_")}
    with open(os.path.join(dump_dir, "devkeys.json")) as f:
        wanted = set(json.load(f))
    missing = sorted(wanted - set(dev))
    if missing:
        sys.exit("Linked issues missing from dev_*.json: " + ", ".join(missing))

    old = by_key(read_dataset(b.OUTPUT_PATH))
    b.fetch_all_issues = lambda: ecs
    b.fetch_issues_by_keys = lambda keys, fields: {k: dev[k] for k in keys if k in dev}
    b.main()
    new = by_key(read_dataset(b.OUTPUT_PATH))

    print(f"Unique tickets: {len(old)} -> {len(new)}")
    for k in sorted(new.keys() - old.keys()):
        t = new[k]
        print(f"ADDED   {k} | {' / '.join(sorted(t['bizs']))} | {t['status']} | due {t['duedate']} | {t['summary']}")
    for k in sorted(old.keys() - new.keys()):
        t = old[k]
        print(f"DROPPED {k} | {' / '.join(sorted(t['bizs']))} | {t['status']} | {t['summary']}")
    for k in sorted(new.keys() & old.keys()):
        a, c = old[k], new[k]
        if a["status"] != c["status"]:
            print(f"STATUS  {k} | {' / '.join(sorted(c['bizs']))} | {a['status']} -> {c['status']}")
        if a["duedate"] != c["duedate"]:
            print(f"DUE     {k} | {a['duedate']} -> {c['duedate']}")
        if a["bizs"] != c["bizs"]:
            print(f"BIZ     {k} | {sorted(a['bizs'])} -> {sorted(c['bizs'])}")


if __name__ == "__main__":
    if len(sys.argv) != 3 or sys.argv[1] not in ("keys", "build"):
        sys.exit(__doc__)
    {"keys": cmd_keys, "build": cmd_build}[sys.argv[1]](sys.argv[2])
