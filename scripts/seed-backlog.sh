#!/usr/bin/env bash
# Seed epics and sub-issues from program/backlog.yaml into GitHub, link the hierarchy,
# and add everything to the Platform Build project with fields populated.
#
# Idempotent: matches on issue title. Safe to re-run after a partial failure, and safe
# to re-run once pending org invitations are accepted - it will fill in the assignees
# it could not set the first time.
#
#   DRY_RUN=1 bash scripts/seed-backlog.sh    # show what would happen
#   bash scripts/seed-backlog.sh              # apply
set -euo pipefail
cd "$(dirname "$0")/.."
exec python3 scripts/seed_backlog.py "$@"
