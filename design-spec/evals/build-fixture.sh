#!/usr/bin/env bash
#
# build-fixture.sh -- build a design-spec eval fixture as a fresh git repository.
#
#   design-spec/evals/build-fixture.sh <eval> <dest>
#
# <eval> is an id from evals.json: 1 to 6, where 5 is eval 3b and may also be
# given as 3b, its label in docs/plans/design-spec.md. <dest> must not exist
# yet; build it outside this repository, in an empty folder of its own. Agent
# output must never land inside this repository.
#
#   1   an empty git repository: `git init` on main, no commits
#   2   an empty project set up with python-code-standards: setup-standards.sh
#       -y --update in a fresh repository, then committed (its pre-commit hooks
#       run on that commit). Needs uv and network; takes a minute or less.
#   3   ParquetToXL at 8ffaa6f (the base of its PR #7), cloned from
#       fixtures/parquettoxl-8ffaa6f.bundle
#   3b  (id 5) fixtures/planted-defects/ committed on main
#   6   the same build as 3b: eval 6 designs a change to that workspace
#   4   ParquetToXL at f8f4a41 (PR #7's merge, which added docs/design.md),
#       cloned from fixtures/parquettoxl-f8f4a41.bundle, with
#       pqx_common/names.py made to import pqx_excel.workbook and committed:
#       the reverse of the excel -> common edge in that design's dependency
#       matrix, so a resync must find a new '!' and a cycle
#
# Commits use a fixed author, committer and date and are never signed, so
# evals 3, 3b and 4 give the same SHAs on every build. No fixture keeps a
# remote: the agent cannot fetch the answer or push. On failure <dest> is
# removed, so the same path can be retried.

set -euo pipefail

if [[ $# -ne 2 ]]; then
    echo "usage: $0 <1|2|3|4|5|3b|6> <dest>" >&2
    exit 2
fi

here="$(cd "$(dirname "$0")" && pwd)"
eval_id="$1"
dest="$2"

[[ ! -e "$dest" ]] || { echo "$dest already exists; pick a new path" >&2; exit 2; }

PARQUETTOXL_BASE="8ffaa6fb173364321977bf8326ccf95982e26bcf"
PARQUETTOXL_DESIGNED="f8f4a41f5e4aae3659f92cf88108bca5c716fa04"

export GIT_AUTHOR_NAME="Fixture" GIT_AUTHOR_EMAIL="fixture@example.invalid"
export GIT_COMMITTER_NAME="Fixture" GIT_COMMITTER_EMAIL="fixture@example.invalid"

built=0
cleanup() {
    if [[ $built -eq 0 && -e "$dest" ]]; then
        rm -rf "$dest"
        echo "removed the partial build at $dest" >&2
    fi
}
trap cleanup EXIT

die() {
    echo "error: $1" >&2
    exit 1
}

commit() {  # commit <message>
    GIT_AUTHOR_DATE="2026-10-16T08:00:00+00:00" GIT_COMMITTER_DATE="2026-10-16T08:00:00+00:00" git -c commit.gpgsign=false commit -q -m "$1"
}

build_empty() {
    mkdir -p "$dest"
    git -C "$dest" init -q -b main
}

build_small_project() {
    local setup="$here/../../python-code-standards/skill/assets/setup-standards.sh"
    [[ -f "$setup" ]] || die "setup script not found at $setup"
    build_empty
    (cd "$dest" && bash "$setup" -y --update && commit "Set up the python-code-standards toolchain")
}

build_parquettoxl() {  # build_parquettoxl <bundle in fixtures/> <commit its main must be at>
    git clone -q -b main "$here/fixtures/$1" "$dest"
    git -C "$dest" remote remove origin
    [[ "$(git -C "$dest" rev-parse HEAD)" == "$2" ]] || die "the bundle's main is not at $2"
}

build_planted_defects() {
    mkdir -p "$dest"
    cp -R "$here/fixtures/planted-defects/." "$dest"
    # safecrlf only silences the warning a core.autocrlf=true user sees for these LF files; what is committed is unchanged.
    (cd "$dest" && git init -q -b main && git -c core.safecrlf=false add -A && commit "tally: daily revenue from an orders CSV")
}

build_resync() {
    build_parquettoxl parquettoxl-f8f4a41.bundle "$PARQUETTOXL_DESIGNED"
    reverse_import
    (cd "$dest" && git -c core.safecrlf=false add -A && commit "pqx-common: import pqx_excel.workbook from names")
}

reverse_import() {  # make pqx_common/names.py import pqx_excel.workbook, which imports names
    local names="packages/pqx-common/src/pqx_common/names.py"
    local workbook="packages/pqx-excel/src/pqx_excel/workbook.py"
    grep -q '^from pqx_common\.names import' "$dest/$workbook" || die "eval 4 expects $workbook to import pqx_common.names; update reverse_import in $0"
    # Appended at the end, not among the imports: workbook imports names, and a
    # top-of-file import would fail at run time in one import order (a partially
    # initialised names). At the end both orders work, so only the design changes.
    # No comment names the eval, so the fixture does not announce the answer. The
    # two blank lines and the suppressions keep the fixture's own gates (Ruff
    # check and format, strict Pyright) as clean as they were at f8f4a41.
    printf '\n\nfrom pqx_excel import workbook  # noqa: E402, F401  # pyright: ignore[reportUnusedImport]\n' >> "$dest/$names"
}

case "$eval_id" in
    1) build_empty ;;
    2) build_small_project ;;
    3) build_parquettoxl parquettoxl-8ffaa6f.bundle "$PARQUETTOXL_BASE" ;;
    3b | 5 | 6) build_planted_defects ;;
    4) build_resync ;;
    *) echo "no eval '$eval_id'; expected 1, 2, 3, 4, 5 (also written 3b), or 6" >&2; exit 2 ;;
esac

built=1
echo "eval $eval_id fixture built at $dest"
git -C "$dest" log --oneline -1 2>/dev/null || echo "(no commits)"
