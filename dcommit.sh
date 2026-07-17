#!/usr/bin/env bash
# dcommit.sh — commit with an explicit date (author + committer synced)
#
# usage:
#   ./dcommit.sh "2024-06-15T14:20"            -> opens editor
#   ./dcommit.sh "2024-06-15T14:20" -m "text"  -> inline message
#   ./dcommit.sh "2024-06-15" -m "text"        -> date-only, time defaults to 14:20
#
# keeps a single timezone across history (edit TZ below if needed)
set -euo pipefail

TZ_OFFSET="+03:00"

raw="${1:-}"; shift || true
if [ -z "$raw" ]; then
  echo "usage: dcommit.sh <YYYY-MM-DD[THH:MM]> [git commit args...]" >&2
  exit 1
fi

# add default time if only a date was given
case "$raw" in
  *T*) stamp="$raw" ;;
  *)   stamp="${raw}T14:20:00" ;;
esac
# add seconds if missing
case "$stamp" in
  *T[0-9][0-9]:[0-9][0-9]:[0-9][0-9]) : ;;
  *T[0-9][0-9]:[0-9][0-9])            stamp="${stamp}:00" ;;
esac

full="${stamp}${TZ_OFFSET}"

GIT_AUTHOR_DATE="$full" GIT_COMMITTER_DATE="$full" git commit "$@"
