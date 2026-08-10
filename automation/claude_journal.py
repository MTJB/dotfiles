#!/usr/bin/env python3
"""
claude_journal.py

Scans local Claude Code session transcripts (~/.claude/projects/**/*.jsonl),
pulls out what happened in the last N hours, summarizes it with a headless
`claude -p` call, and writes a daily journal entry into an Obsidian vault.

Usage:
    python3 claude_journal.py                 # normal run, summarizes the previous calendar day
    python3 claude_journal.py --since-hours 168   # rolling-window run (e.g. weekly-style), dated today
    python3 claude_journal.py --dry-run        # print digest, don't call claude or write file

Designed to run daily at 11am via launchd (see com.mark.claudejournal.plist),
summarizing the prior calendar day. Pass --since-hours for an ad-hoc rolling
window instead.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path

# ---- Configuration -------------------------------------------------------

CLAUDE_PROJECTS_DIR = Path.home() / ".claude" / "projects"
VAULT_JOURNAL_DIR = Path(
    "/Users/mark/Library/Mobile Documents/iCloud~md~obsidian/Documents/Notes/05 Reference/Journal"
)
LOG_FILE = Path.home() / ".claude" / "journal.log"

# Tool names whose inputs we bother extracting file paths from
FILE_TOOLS = {"Read", "Write", "Edit", "NotebookEdit"}


def log(msg: str) -> None:
    ts = datetime.now().isoformat(timespec="seconds")
    line = f"[{ts}] {msg}"
    print(line)
    try:
        with LOG_FILE.open("a") as f:
            f.write(line + "\n")
    except Exception:
        pass


def readable_project_name(encoded_dir_name: str) -> str:
    """
    Best-effort decode of Claude Code's project directory encoding
    (slashes -> dashes). This is heuristic, not exact, since real
    directory/repo names can also contain dashes.
    """
    name = encoded_dir_name
    prefix = "-Users-mark-Code-"
    if name.startswith(prefix):
        return name[len(prefix):]
    return name.lstrip("-")


def extract_text_from_content(content) -> str:
    """Pull plain text out of a message content field (str or list of blocks)."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if not isinstance(block, dict):
                continue
            btype = block.get("type")
            if btype == "text":
                parts.append(block.get("text", ""))
        return "\n".join(p for p in parts if p)
    return ""


def parse_session(path: Path, since: datetime, until: datetime) -> dict | None:
    """Parse one session JSONL file. Returns a digest dict, or None if
    the session has no activity in [`since`, `until`)."""
    first_user_msg = None
    tool_names = set()
    files_touched = set()
    commands_run = []
    last_ts = None
    first_ts = None
    activity_after_cutoff = False

    try:
        with path.open("r", errors="ignore") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue

                ts_raw = obj.get("timestamp")
                ts = None
                if ts_raw:
                    try:
                        ts = datetime.fromisoformat(ts_raw.replace("Z", "+00:00"))
                    except ValueError:
                        ts = None
                if ts:
                    if first_ts is None:
                        first_ts = ts
                    last_ts = ts
                    ts_local = ts.astimezone().replace(tzinfo=None) if ts.tzinfo else ts
                    if since <= ts_local < until:
                        activity_after_cutoff = True

                otype = obj.get("type")
                message = obj.get("message", {}) if isinstance(obj.get("message"), dict) else {}

                if otype == "user" and first_user_msg is None:
                    text = extract_text_from_content(message.get("content"))
                    if text:
                        first_user_msg = text.strip().splitlines()[0][:200]

                content = message.get("content")
                if isinstance(content, list):
                    for block in content:
                        if not isinstance(block, dict):
                            continue
                        if block.get("type") == "tool_use":
                            tname = block.get("name", "unknown")
                            tool_names.add(tname)
                            tinput = block.get("input", {}) or {}
                            if tname in FILE_TOOLS:
                                fp = tinput.get("file_path") or tinput.get("path")
                                if fp:
                                    files_touched.add(fp)
                            if tname == "Bash":
                                cmd = tinput.get("command")
                                if cmd:
                                    commands_run.append(cmd[:120])
    except Exception as e:
        log(f"  ! failed to parse {path.name}: {e}")
        return None

    # fall back to file mtime if no activity found via timestamps but file is recent
    if last_ts is None:
        mtime = datetime.fromtimestamp(path.stat().st_mtime)
        if since <= mtime < until:
            activity_after_cutoff = True
        last_ts = mtime

    if not activity_after_cutoff:
        return None

    return {
        "session_id": path.stem,
        "first_user_msg": first_user_msg or "(no user message found)",
        "tool_names": sorted(tool_names),
        "files_touched": sorted(files_touched)[:25],
        "commands_run": commands_run[:15],
        "last_activity": last_ts,
    }


def collect_digests(since: datetime, until: datetime) -> dict[str, list[dict]]:
    """Returns {project_name: [session_digest, ...]}"""
    results: dict[str, list[dict]] = {}

    if not CLAUDE_PROJECTS_DIR.exists():
        log(f"No projects directory found at {CLAUDE_PROJECTS_DIR}")
        return results

    for project_dir in CLAUDE_PROJECTS_DIR.iterdir():
        if not project_dir.is_dir():
            continue
        project_name = readable_project_name(project_dir.name)

        for jsonl_file in project_dir.glob("*.jsonl"):
            try:
                if datetime.fromtimestamp(jsonl_file.stat().st_mtime) < since - timedelta(days=1):
                    # cheap skip for very old files, avoids parsing everything every run
                    continue
            except OSError:
                continue

            digest = parse_session(jsonl_file, since, until)
            if digest:
                results.setdefault(project_name, []).append(digest)

    return results


def build_digest_text(digests: dict[str, list[dict]]) -> str:
    lines = []
    for project, sessions in sorted(digests.items()):
        lines.append(f"## Project: {project}")
        for s in sessions:
            lines.append(f"- Session {s['session_id']} (last activity {s['last_activity']})")
            lines.append(f"  - Opened with: {s['first_user_msg']}")
            if s["tool_names"]:
                lines.append(f"  - Tools used: {', '.join(s['tool_names'])}")
            if s["files_touched"]:
                lines.append(f"  - Files touched: {', '.join(s['files_touched'])}")
            if s["commands_run"]:
                lines.append(f"  - Commands run: {'; '.join(s['commands_run'])}")
        lines.append("")
    return "\n".join(lines)


SUMMARY_PROMPT = """You are helping write a concise daily engineering journal entry.
Below is a raw digest of Claude Code sessions from today, grouped by project.
Turn this into a tight markdown summary:

- Group by project (use the project names given)
- Under each project, a few bullet points on what was actually worked on
  (infer intent from the opening message, files touched, and commands run
  — don't just restate the raw log)
- Skip trivial or exploratory sessions with no real output
- No preamble, no "Here is your summary" framing — start directly with the
  first project heading
- Keep it factual and terse, this is a personal log, not a report

Raw digest:

{digest}
"""


def summarize_with_claude(digest_text: str) -> str:
    prompt = SUMMARY_PROMPT.format(digest=digest_text)
    try:
        result = subprocess.run(
            ["claude", "-p", prompt],
            capture_output=True,
            text=True,
            timeout=180,
        )
    except FileNotFoundError:
        log("! `claude` CLI not found on PATH — is Claude Code installed?")
        return digest_text
    except subprocess.TimeoutExpired:
        log("! claude -p timed out, falling back to raw digest")
        return digest_text

    if result.returncode != 0:
        log(f"! claude -p failed: {result.stderr.strip()[:300]}")
        return digest_text

    return result.stdout.strip()


BACKLINK_PROMPT = """Add Obsidian wiki-links to the journal entry below, which will be
inserted into an Obsidian vault.

Wrap these in [[ ]] if they appear as plain, unlinked text:
- Product and tool names: SPM, CIM, IDM, MAP, MCP, FedRAMP, Wiz, Grafana, Slack,
  Confluence, Jira, Figma, Rovo, Obsidian, Power Automate, Salesforce, NetSuite,
  Snyk, etc.
- Internal project/feature codenames: Red Octopus, Planeshift, Contractor Walls,
  ATF, GRIP, PLG, FeatureFlex, etc.
- iManage concepts and components: CDEAR, IRM, Hazelcast, AuditHub, Purview, OTS, etc.

Do NOT link:
- People's names
- Anything already wrapped in [[ ]]
- Generic words, job titles, team names
- Very granular internal identifiers (table names, config keys, code identifiers)
  — only link a term if it plausibly has its own vault note

Do not add, remove, or rephrase any content — only wrap existing terms in [[ ]].
Return ONLY the resulting markdown text, with no preamble, no code fences, and
no commentary.

Text:

{entry}
"""


def add_backlinks_with_claude(entry_text: str) -> str:
    prompt = BACKLINK_PROMPT.format(entry=entry_text)
    try:
        result = subprocess.run(
            ["claude", "-p", prompt],
            capture_output=True,
            text=True,
            timeout=180,
        )
    except FileNotFoundError:
        log("! `claude` CLI not found on PATH — skipping backlinks")
        return entry_text
    except subprocess.TimeoutExpired:
        log("! claude -p timed out on backlinking, falling back to unlinked text")
        return entry_text

    if result.returncode != 0:
        log(f"! claude -p failed on backlinking: {result.stderr.strip()[:300]}")
        return entry_text

    return result.stdout.strip()


def write_journal_entry(summary: str, date_str: str, dry_run: bool) -> None:
    VAULT_JOURNAL_DIR.mkdir(parents=True, exist_ok=True)
    out_path = VAULT_JOURNAL_DIR / f"{date_str}.md"

    header = f"# {date_str} — Claude Code Journal\n\n"
    body = header + summary + "\n"

    if dry_run:
        log(f"[dry-run] would write to {out_path}:\n{body}")
        return

    if out_path.exists():
        existing = out_path.read_text()
        body = existing.rstrip() + "\n\n---\n\n" + summary + "\n"

    out_path.write_text(body)
    log(f"Wrote journal entry to {out_path}")


def main():
    parser = argparse.ArgumentParser(description="Summarize Claude Code sessions into a daily journal.")
    parser.add_argument(
        "--since-hours",
        type=float,
        default=None,
        help="Look back this many hours from now (rolling window, dated today). "
        "If omitted, summarizes the previous calendar day instead.",
    )
    parser.add_argument("--dry-run", action="store_true", help="Print digest/summary, don't write or call claude")
    args = parser.parse_args()

    now = datetime.now()

    if args.since_hours is None:
        yesterday = (now - timedelta(days=1)).date()
        since = datetime.combine(yesterday, datetime.min.time())
        until = since + timedelta(days=1)
        date_str = yesterday.strftime("%Y-%m-%d")
    else:
        since = now - timedelta(hours=args.since_hours)
        until = now
        date_str = now.strftime("%Y-%m-%d")

    log(f"Starting journal run, window {since} to {until}")
    digests = collect_digests(since, until)

    if not digests:
        log("No session activity found in window — nothing to write.")
        return

    digest_text = build_digest_text(digests)

    if args.dry_run:
        log("=== RAW DIGEST ===\n" + digest_text)

    if args.dry_run:
        summary = digest_text
    else:
        summary = summarize_with_claude(digest_text)
        summary = add_backlinks_with_claude(summary)

    write_journal_entry(summary, date_str, args.dry_run)


if __name__ == "__main__":
    sys.exit(main())
