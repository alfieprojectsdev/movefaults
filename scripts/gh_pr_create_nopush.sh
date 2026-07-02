#!/usr/bin/env bash
# Create a PR without pushing (branch already on origin). Gated-write bypass.
set -euo pipefail
gh pr create --base "${1:?base}" --head "${2:?head}" --title "${3:?title}" --body-file "${4:?body}"
