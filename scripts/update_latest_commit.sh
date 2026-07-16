#!/usr/bin/env bash
# Updates the "LATEST COMMIT" panel and LAST SYNC timestamp inside header.svg
# using the real-time GitHub Events API for krishankshh (includes private repo
# activity because the request is authenticated as that user).
set -euo pipefail

USERNAME="krishankshh"
SVG_FILE="header.svg"

if [ -z "${GH_TOKEN:-}" ]; then
  echo "ERROR: GH_TOKEN is not set. Add a repo secret named PROFILE_PAT and pass it in the workflow." >&2
  exit 1
fi

echo "Fetching recent events for $USERNAME..."
curl -sf -H "Authorization: token $GH_TOKEN" \
        -H "Accept: application/vnd.github+json" \
        "https://api.github.com/users/$USERNAME/events?per_page=20" -o events.json

# Find the most recent PushEvent (works for private repos too, since we're
# authenticated as the user themself).
REPO_NAME=$(jq -r '[.[] | select(.type=="PushEvent")][0].repo.name // empty' events.json)
COMMIT_MSG=$(jq -r '[.[] | select(.type=="PushEvent")][0].payload.commits[-1].message // empty' events.json)
COMMIT_TIME_RAW=$(jq -r '[.[] | select(.type=="PushEvent")][0].created_at // empty' events.json)

if [ -z "$REPO_NAME" ]; then
  echo "No recent PushEvent found — leaving header.svg unchanged."
  exit 0
fi

# Strip the owner prefix ("krishankshh/Meraki" -> "Meraki")
REPO_SHORT="${REPO_NAME#*/}"
# Truncate commit message to keep the panel tidy
COMMIT_MSG_SHORT=$(echo "$COMMIT_MSG" | head -n1 | cut -c1-70)
COMMIT_TIME_FMT=$(date -u -d "$COMMIT_TIME_RAW" +"%b %d, %Y %H:%M UTC" 2>/dev/null || echo "$COMMIT_TIME_RAW")
SYNC_TIME_FMT=$(date -u +"%b %d, %Y %H:%M UTC")

python3 - "$SVG_FILE" "$REPO_SHORT" "$COMMIT_MSG_SHORT" "$COMMIT_TIME_FMT" "$SYNC_TIME_FMT" << 'PYEOF'
import re, sys, html

svg_path, repo, msg, ctime, synctime = sys.argv[1:6]

def esc(s):
    return html.escape(s, quote=False)

with open(svg_path, encoding="utf-8") as f:
    svg = f.read()

def replace_between(text, start_marker, end_marker, new_value):
    pattern = re.compile(re.escape(start_marker) + r'.*?' + re.escape(end_marker), re.S)
    return pattern.sub(start_marker + esc(new_value) + end_marker, text, count=1)

svg = replace_between(svg, "<!--REPO_START-->", "<!--REPO_END-->", repo)
svg = replace_between(svg, "<!--MSG_START-->", "<!--MSG_END-->", msg or "(no message)")
svg = replace_between(svg, "<!--TIME_START-->", "<!--TIME_END-->", ctime)
svg = replace_between(svg, "<!--SYNC_START-->", "<!--SYNC_END-->", synctime)

with open(svg_path, "w", encoding="utf-8") as f:
    f.write(svg)

print(f"Updated panel: {repo} — {msg[:40]!r} @ {ctime}")
PYEOF

rm -f events.json
