#!/usr/bin/env python3
import argparse
import datetime as dt
import html
import json
import os
import re
import subprocess
import sys
from pathlib import Path
import urllib.error
import urllib.parse
import urllib.request


BASE_URL = "https://xindong.atlassian.net"
DEFAULT_SPACE_ID = "7656119595979246772"
DEFAULT_ROOT_NODE = "C6tcwyaDRidEHikTGSzcZDAJnOg"
DEFAULT_ACCOUNT_NAME = "宋典灿 songdiancan"
DEFAULT_WEEKLY_URL = "https://xd.feishu.cn/wiki/Ahk9wA2vnibzMKk6xGrc26n2nfh"


def run(cmd, check=True):
    result = subprocess.run(
        [str(x) for x in cmd],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if check and result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()
        raise SystemExit(f"Command failed ({result.returncode}): {' '.join(str(x) for x in cmd)}\n{detail}")
    return result.stdout, result.stderr, result.returncode


def normalize_issue_key(value):
    match = re.search(r"[A-Z][A-Z0-9]+-\d+", value)
    if not match:
        raise SystemExit(f"Could not find Jira issue key in: {value}")
    return match.group(0)


def parse_date(value):
    if value:
        return dt.datetime.strptime(value, "%Y-%m-%d").date()
    return dt.date.today()


def week_range(day):
    start = day - dt.timedelta(days=day.weekday())
    end = start + dt.timedelta(days=4)
    return start, end


def format_m_d(day):
    return f"{day.month}.{day.day}"


def weekly_title(day):
    start, end = week_range(day)
    end_text = f"{end.year}.{format_m_d(end)}" if end.year != start.year else format_m_d(end)
    return f"程序周报{start.year}.{format_m_d(start)}-{end_text}"


def fiscal_quarter(day):
    return (day.month - 1) // 3 + 1


def strip_xml_tags(value):
    value = re.sub(r"<[^>]+>", "", value)
    return html.unescape(re.sub(r"\s+", "", value))


def load_json_from_stdout(stdout):
    start = stdout.find("{")
    if start < 0:
        raise SystemExit(f"Expected JSON output, got: {stdout[:500]}")
    return json.loads(stdout[start:])


def lark_json(args):
    stdout, _, _ = run(["opencli", "lark-cli", *args])
    return load_json_from_stdout(stdout)


def load_shell_env():
    result = subprocess.run(
        ["zsh", "-lc", "source ~/.zshrc >/dev/null 2>&1 || true; env"],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    for line in result.stdout.splitlines():
        if "=" in line:
            key, value = line.split("=", 1)
            os.environ.setdefault(key, value)


def jira_auth_header():
    load_shell_env()
    email = os.environ.get("ATLASSIAN_EMAIL")
    token = os.environ.get("ATLASSIAN_API_TOKEN")
    if not email or not token:
        raise SystemExit("Missing ATLASSIAN_EMAIL or ATLASSIAN_API_TOKEN after loading ~/.zshrc")
    import base64

    encoded = base64.b64encode(f"{email}:{token}".encode()).decode()
    return {"Authorization": f"Basic {encoded}", "Accept": "application/json"}


def read_issue_summary(issue_key):
    path = f"/rest/api/3/issue/{issue_key}?fields={urllib.parse.quote('summary')}"
    req = urllib.request.Request(BASE_URL + path, method="GET", headers=jira_auth_header())
    try:
        with urllib.request.urlopen(req, timeout=45) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise SystemExit(f"Jira HTTP {exc.code}: {detail}") from exc
    summary = ((data.get("fields") or {}).get("summary") or "").strip()
    if not summary:
        raise SystemExit(f"Jira issue {issue_key} has no summary in response")
    return summary


def list_wiki_children(space_id, parent_node):
    data = lark_json([
        "wiki", "+node-list",
        "--space-id", space_id,
        "--parent-node-token", parent_node,
        "--page-all",
        "--format", "json",
    ])
    return ((data.get("data") or {}).get("nodes") or [])


def find_child_by_title(space_id, parent_node, title):
    for node in list_wiki_children(space_id, parent_node):
        if node.get("title") == title:
            return node
    return None


def resolve_weekly_node(day, space_id, root_node, weekly_url=None):
    title = weekly_title(day)
    if weekly_url:
        return {"node_token": weekly_url, "title": title, "url": weekly_url}

    year_title = f"程序{day.year}年周报"
    year_node = find_child_by_title(space_id, root_node, year_title)
    if year_node is None:
        raise SystemExit(f"Could not find Feishu weekly report year node: {year_title}")

    quarter_title = f"程序{day.year}年周报Q{fiscal_quarter(day)}"
    quarter_node = find_child_by_title(space_id, year_node["node_token"], quarter_title)
    if quarter_node is None:
        raise SystemExit(f"Could not find Feishu weekly report quarter node: {quarter_title}")

    week_node = find_child_by_title(space_id, quarter_node["node_token"], title)
    if week_node is None:
        raise SystemExit(f"Could not find Feishu weekly report page titled: {title}")
    return week_node


def fetch_doc_xml(doc):
    data = lark_json([
        "docs", "+fetch",
        "--doc", doc,
        "--detail", "with-ids",
        "--doc-format", "xml",
        "--format", "json",
    ])
    return (((data.get("data") or {}).get("document") or {}).get("content") or "")


def find_tag_spans(xml, tag_name):
    return list(re.finditer(rf"<{tag_name}\b[^>]*>.*?</{tag_name}>", xml, re.S))


def find_cell_spans(row_xml):
    return list(re.finditer(r"<t[dh]\b[^>]*>.*?</t[dh]>", row_xml, re.S))


def date_column(header_row, day):
    target = format_m_d(day)
    cells = find_cell_spans(header_row)
    for index, cell in enumerate(cells):
        if strip_xml_tags(cell.group(0)) == target:
            return index
    header = " | ".join(strip_xml_tags(cell.group(0)) for cell in cells)
    raise SystemExit(f"Could not find date column {target}; header cells: {header}")


def row_for_account(rows, account_name):
    normalized_account = re.sub(r"\s+", "", account_name).lower()
    for row in rows:
        first_cell = find_cell_spans(row.group(0))[0].group(0)
        text = strip_xml_tags(first_cell)
        if normalized_account in re.sub(r"\s+", "", text).lower():
            return row
    raise SystemExit(f"Could not find weekly report row for account: {account_name}")


def cell_inner(cell_xml):
    match = re.match(r"<t[dh]\b[^>]*>(.*)</t[dh]>", cell_xml, re.S)
    if not match:
        raise SystemExit("Could not parse target table cell.")
    return match.group(1)


def first_paragraph_id(cell_xml):
    match = re.search(r"<p\b[^>]*\bid=\"([^\"]+)\"", cell_xml)
    if not match:
        raise SystemExit("Could not find target paragraph id in weekly report cell.")
    return match.group(1)


def is_effectively_empty_cell(cell_xml):
    return strip_xml_tags(cell_xml) == ""


def jira_issue_link(issue_key, summary):
    href = html.escape(f"{BASE_URL}/browse/{issue_key}", quote=True)
    label = html.escape(f"{issue_key}{summary}")
    return f'<a href="{href}">{label}</a>'


def build_replacement_content(cell_xml, issue_key, summary):
    link = jira_issue_link(issue_key, summary)
    if f"/browse/{issue_key}" in cell_xml or f">{issue_key}<" in cell_xml:
        return None
    if is_effectively_empty_cell(cell_xml):
        return f"<p>{link}</p>"
    inner = cell_inner(cell_xml)
    return f"{inner}<p>{link}</p>"


def update_doc_block(doc, block_id, content, dry_run=False):
    cmd = [
        "opencli", "lark-cli", "docs", "+update",
        "--doc", doc,
        "--command", "block_replace",
        "--block-id", block_id,
        "--content", content,
        "--format", "json",
    ]
    if dry_run:
        print("+ " + " ".join(cmd + ["--dry-run"]))
        return
    stdout, _, _ = run(cmd)
    load_json_from_stdout(stdout)


def update_weekly(doc, day, account_name, issue_key, summary, dry_run=False):
    xml = fetch_doc_xml(doc)
    rows = find_tag_spans(xml, "tr")
    if not rows:
        raise SystemExit("Could not find any table rows in Feishu weekly report page.")
    col = date_column(rows[0].group(0), day)
    target_row = row_for_account(rows, account_name)
    cells = find_cell_spans(target_row.group(0))
    if col >= len(cells):
        raise SystemExit(f"Target row has only {len(cells)} cells; date column index is {col}.")
    target_cell = cells[col].group(0)
    content = build_replacement_content(target_cell, issue_key, summary)
    target = f"{weekly_title(day)}#{format_m_d(day)}#{account_name}"
    if content is None:
        print(f"weekly_report skipped: {issue_key} already exists in {target}")
        return
    block_id = first_paragraph_id(target_cell)
    if dry_run:
        print(f"weekly_report dry-run: would add {issue_key} to {target} at block {block_id}")
        return
    update_doc_block(doc, block_id, content, dry_run=False)
    print(f"weekly_report updated: added {issue_key} to {target}")


def main():
    parser = argparse.ArgumentParser(description="Add a Jira issue to the Feishu programming weekly report.")
    parser.add_argument("issue", help="Jira issue key or URL")
    parser.add_argument("--date", help="Report date in YYYY-MM-DD. Defaults to today.")
    parser.add_argument("--account-name", default=DEFAULT_ACCOUNT_NAME)
    parser.add_argument("--space-id", default=DEFAULT_SPACE_ID)
    parser.add_argument("--root-node", default=DEFAULT_ROOT_NODE)
    parser.add_argument("--weekly-url", default=os.environ.get("JIRA_WEEKLY_REPORT_FEISHU_URL"))
    parser.add_argument("--summary", help="Jira issue summary. Defaults to reading Jira.")
    parser.add_argument("--dry-run", action="store_true", help="Check and print the target without updating Feishu.")
    args = parser.parse_args()

    issue_key = normalize_issue_key(args.issue)
    summary = (args.summary or "").strip() or read_issue_summary(issue_key)
    day = parse_date(args.date)
    node = resolve_weekly_node(
        day,
        args.space_id,
        args.root_node,
        weekly_url=args.weekly_url,
    )
    doc = node.get("node_token") or node.get("url")
    update_weekly(doc, day, args.account_name, issue_key, summary, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
