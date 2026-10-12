#!/usr/bin/env bash
#
# run-headless.sh -- run one nightshift eval night without a terminal.
#
#   nightshift/evals/run-headless.sh <fixture-dir> <out-dir>
#
# Runs `claude -p /nightshift` in <fixture-dir> under auto mode, with a session id
# of its own, and stands in for the watchdog: if a run ends before the log says
# `Status: complete`, it resumes the same session with /nightshift again, at most
# five runs. The scheduled watchdog itself is not exercised, since it dies with
# each headless run.
#
# <out-dir> receives session-id.txt, driver.log, and run-N.jsonl / run-N.err
# (stream-json output). The transcript is also kept under ~/.claude/projects/.
# Exits 0 once the log says complete, 1 if five runs end without that, and 2 on
# bad arguments or a failed setup step. Needs uv, which generates the session id.
#
# Stopping this script does not stop a claude process it started; end that
# process too, or it keeps working in the fixture.

set -u

if [[ $# -ne 2 ]]; then
    echo "usage: $0 <fixture-dir> <out-dir>" >&2
    exit 2
fi

fixture="$1"
out="$(mkdir -p "$2" && cd "$2" && pwd)"
cd "$fixture" || exit 2

# Git Bash rewrites an argument starting with "/" into a Windows path. Exempt only
# /nightshift: MSYS_NO_PATHCONV=1 would also stop the night's own shells from
# converting /c/... paths, which native programs such as node cannot resolve.
export MSYS2_ARG_CONV_EXCL="/nightshift"

id="$(uv run --no-project python -c 'import uuid; print(uuid.uuid4())')"
[[ -n "$id" ]] || { echo "could not generate a session id with uv" >&2; exit 2; }
echo "$id" > "$out/session-id.txt"

# Logs are named LOG-<YYYY-MM-DD>.md, so the last glob match is the newest night.
status() {
    local logs=(.nightshift/LOG-*.md)
    sed -n 's/^Status: //p' "${logs[-1]}" 2>/dev/null
}

for i in 1 2 3 4 5; do
    if [[ $i -eq 1 ]]; then session=(--session-id "$id"); else session=(--resume "$id"); fi
    echo "run $i start $(date +%T)" >> "$out/driver.log"
    timeout 4h claude -p "/nightshift" "${session[@]}" --permission-mode auto \
        --output-format stream-json --verbose > "$out/run-$i.jsonl" 2> "$out/run-$i.err"
    echo "run $i exit $? at $(date +%T); status: $(status)" >> "$out/driver.log"
    [[ "$(status)" == complete ]] && break
done
echo "driver done $(date +%T)" >> "$out/driver.log"
[[ "$(status)" == complete ]] || { echo "the night did not complete; see $out/driver.log" >&2; exit 1; }
