#!/usr/bin/env python3
"""Regenerate every data panel in header.svg from live GitHub data.

Regions are delimited by <!--NAME_START--> / <!--NAME_END--> comment markers:
heatmap cells, contribution total, language donut + legend, monthly bars,
repository roster, footer stats, latest-commit panel, sync timestamp.
Needs GH_TOKEN (classic PAT or fine-grained token) in the environment.
"""
import html
import json
import math
import os
import re
import sys
import urllib.request
from datetime import datetime, timezone

USERNAME = "krishankshh"
SVG_FILE = sys.argv[1] if len(sys.argv) > 1 else "header.svg"
PROFILE_REPO = f"{USERNAME}/{USERNAME}"

TOKEN = os.environ.get("GH_TOKEN")
if not TOKEN:
    sys.exit("ERROR: GH_TOKEN is not set")

LANG_COLORS = {
    "HTML": "#e34c26", "TypeScript": "#3178c6", "Python": "#3572A5",
    "CSS": "#563d7c", "JavaScript": "#f1e05a", "Solidity": "#AA6746",
    "PHP": "#4F5D95", "Shell": "#89e051", "C": "#555555", "C++": "#f34b7d",
    "C#": "#178600", "Java": "#b07219", "Go": "#00ADD8", "Rust": "#dea584",
    "Ruby": "#701516", "Kotlin": "#A97BFF", "Swift": "#F05138",
    "Dart": "#00B4AB", "Jupyter Notebook": "#DA5B0B", "Vue": "#41b883",
    "SCSS": "#c6538c",
}
OTHER_COLOR = "#5a6b78"


def api(url, data=None):
    req = urllib.request.Request(
        url,
        data=json.dumps(data).encode() if data else None,
        headers={
            "Authorization": f"Bearer {TOKEN}",
            "Accept": "application/vnd.github+json",
            "User-Agent": USERNAME,
        },
    )
    with urllib.request.urlopen(req) as r:
        return json.loads(r.read())


def esc(s):
    return html.escape(s, quote=False)


# ---------------------------------------------------------------- fetch data
gql = api("https://api.github.com/graphql", {
    "query": """
    query($login: String!) {
      user(login: $login) {
        followers { totalCount }
        contributionsCollection {
          contributionCalendar {
            totalContributions
            weeks { contributionDays { date contributionCount } }
          }
        }
      }
    }""",
    "variables": {"login": USERNAME},
})
user = gql["data"]["user"]
calendar = user["contributionsCollection"]["contributionCalendar"]
followers = user["followers"]["totalCount"]

# ponytail: one page covers <=100 repos, paginate if the account outgrows it
repos = api(f"https://api.github.com/users/{USERNAME}/repos?per_page=100&type=owner")

events = api(f"https://api.github.com/users/{USERNAME}/events?per_page=100")

# ------------------------------------------------------------ build regions
def cell_color(c):
    if c == 0:
        return "#0d2b21"
    if c <= 2:
        return "#0f5c3f"
    if c <= 5:
        return "#159a5c"
    if c <= 9:
        return "#22c76e"
    return "#5dffa8"


weeks = calendar["weeks"][-53:]
heatmap = "".join(
    f'<rect x="{279 + 8 * wi:.1f}" y="{136 + 8 * di:.1f}" width="6.4" height="6.4" '
    f'rx="1.2" fill="{cell_color(d["contributionCount"])}"/>'
    for wi, w in enumerate(weeks)
    for di, d in enumerate(w["contributionDays"])
)

# Monthly totals from the same calendar (contributions per calendar month)
months = {}
for w in weeks:
    for d in w["contributionDays"]:
        months.setdefault(d["date"][:7], 0)
        months[d["date"][:7]] += d["contributionCount"]
month_keys = sorted(months)[-13:]
max_m = max((months[k] for k in month_keys), default=0) or 1
monthly = ""
for i, k in enumerate(month_keys):
    h = 90 * months[k] / max_m
    monthly += (
        f'<rect x="{37 + 14.45 * i:.1f}" y="{502 - h:.1f}" width="11.5" height="{h:.1f}" '
        f'rx="1.5" fill="#22c76e" opacity="{0.5 + 0.35 * months[k] / max_m:.2f}"/>'
        f'<text x="{42.2 + 14.45 * i:.1f}" y="515" text-anchor="middle" class="panel-dim" '
        f'font-size="7.6">{k[5:]}</text>'
    )

# Language mix: primary language per repo, top 7 + Other
lang_counts = {}
for r in repos:
    if r["language"]:
        lang_counts[r["language"]] = lang_counts.get(r["language"], 0) + 1
ranked = sorted(lang_counts.items(), key=lambda kv: -kv[1])
if len(ranked) > 8:
    ranked = ranked[:7] + [("Other", sum(c for _, c in ranked[7:]))]
total_langs = sum(c for _, c in ranked) or 1


def pt(r, ang):
    return f"{820 + r * math.cos(ang):.2f},{192 + r * math.sin(ang):.2f}"


langmix = ""
ang = -math.pi / 2
for name, count in ranked:
    sweep = 2 * math.pi * count / total_langs
    sweep = min(sweep, 2 * math.pi - 1e-4)  # a lone slice still needs two arc points
    a0, a1 = ang, ang + sweep
    ang = a1
    color = LANG_COLORS.get(name, OTHER_COLOR)
    large = 1 if sweep > math.pi else 0
    langmix += (
        f'<path d="M{pt(52, a0)} A52,52 0 {large} 1 {pt(52, a1)} L{pt(30, a1)} '
        f'A30,30 0 {large} 0 {pt(30, a0)} Z" fill="{color}" opacity="0.92" '
        f'stroke="#04100b" stroke-width="1"/>'
    )
langmix += (
    f'<text x="820" y="190" text-anchor="middle" class="panel-value" font-size="17">{len(repos)}</text>'
    f'<text x="820" y="204" text-anchor="middle" class="panel-dim" font-size="8">REPOS</text>'
)
for i, (name, count) in enumerate(ranked):
    cy = 148 + 16.5 * i
    langmix += (
        f'<circle cx="892" cy="{cy:.1f}" r="3.4" fill="{LANG_COLORS.get(name, OTHER_COLOR)}"/>'
        f'<text x="902" y="{cy + 3.5:.1f}" class="panel-text" font-size="10.5">{esc(name)}</text>'
        f'<text x="964" y="{cy + 3.5:.1f}" text-anchor="end" class="panel-dim" font-size="10">{count}</text>'
    )

# Roster: 6 most recently pushed repos, profile repo excluded (bot noise)
work = [r for r in repos if r["full_name"] != PROFILE_REPO]
work.sort(key=lambda r: r["pushed_at"] or "", reverse=True)
roster = ""
for i, r in enumerate(work[:6]):
    y = 618 + 22 * i
    lang = r["language"] or "—"
    roster += (
        f'<text x="36" y="{y}" class="panel-text" font-size="10.5">{esc(r["name"][:34])}</text>'
        f'<circle cx="314" cy="{y - 3.5}" r="3" fill="{LANG_COLORS.get(lang, OTHER_COLOR)}"/>'
        f'<text x="324" y="{y}" class="panel-text" font-size="10">{esc(lang)}</text>'
        f'<text x="538" y="{y}" text-anchor="end" class="panel-text" font-size="10">{r["stargazers_count"]}</text>'
        f'<text x="628" y="{y}" text-anchor="end" class="panel-text" font-size="10">{r["forks_count"]}</text>'
        f'<text x="962" y="{y}" text-anchor="end" class="panel-dim" font-size="9.5">{r["pushed_at"][:10]}</text>'
    )
more = f"+{max(len(work) - 6, 0)} MORE NOT SHOWN"

stars = sum(r["stargazers_count"] for r in repos)
forks = sum(r["forks_count"] for r in repos)
sep = " · "
stats = (
    f"{len(repos)} REPOS{sep}{stars} STAR{'S' if stars != 1 else ''}{sep}"
    f"{forks} FORK{'S' if forks != 1 else ''}{sep}"
    f"{calendar['totalContributions']} CONTRIB/YR (PUBLIC){sep}{followers} FOLLOWERS"
)

# Latest commit: newest push outside the profile repo. Event payloads no
# longer carry commit details, so resolve the head SHA separately.
push = next(
    (e for e in events
     if e["type"] == "PushEvent" and e["repo"]["name"] != PROFILE_REPO
     and e["payload"].get("head")),
    None,
)
head_commit = None
if push:
    try:
        head_commit = api(
            f"https://api.github.com/repos/{push['repo']['name']}/commits/{push['payload']['head']}"
        )
    except Exception:
        push = None  # head unreachable (force push / deleted branch): keep old panel
sync_fmt = "%b %d, %Y %H:%M UTC"
now = datetime.now(timezone.utc).strftime(sync_fmt)

# -------------------------------------------------------------- write file
with open(SVG_FILE, encoding="utf-8") as f:
    svg = f.read()


def fill(name, value):
    global svg
    start, end = f"<!--{name}_START-->", f"<!--{name}_END-->"
    pattern = re.compile(re.escape(start) + ".*?" + re.escape(end), re.S)
    svg, n = pattern.subn(start + value + end, svg, count=1)
    if n != 1:
        sys.exit(f"ERROR: marker {name} not found in {SVG_FILE}")


fill("HEATMAP", heatmap)
fill("CTOTAL", str(calendar["totalContributions"]))
fill("LANGMIX", langmix)
fill("MONTHLY", monthly)
fill("ROSTER", roster)
fill("RMORE", more)
fill("STATS", stats)
fill("SYNC", now)
if push:
    fill("REPO", esc(push["repo"]["name"].split("/", 1)[1]))
    fill("MSG", esc(head_commit["commit"]["message"].splitlines()[0][:70]))
    t = datetime.strptime(push["created_at"], "%Y-%m-%dT%H:%M:%SZ")
    # short format: anything longer collides with the AUTO-SYNCED badge at x=964
    fill("TIME", t.strftime("%Y-%m-%d %H:%M"))

with open(SVG_FILE, "w", encoding="utf-8", newline="\n") as f:
    f.write(svg)
print(f"Dashboard updated: {len(repos)} repos, {calendar['totalContributions']} contributions, "
      f"latest push: {push['repo']['name'] if push else 'none'}")
