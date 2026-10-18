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
#   4   template-sqlmesh-duckdb cloned from GitHub, with ports.py made to import
#       from adapters and committed. Fails while the template has no
#       docs/design.md, since there is then no design to resync.
#       DESIGN_SPEC_TEMPLATE_URL overrides the clone URL (to test this case
#       against a local copy).
#
# Commits use a fixed author, committer and date, so evals 3 and 3b give the
# same SHAs on every build. No fixture keeps a remote: the agent cannot fetch
# the answer or push. On failure <dest> is removed, so the same path can be
# retried.

set -euo pipefail

if [[ $# -ne 2 ]]; then
    echo "usage: $0 <1|2|3|4|5|3b|6> <dest>" >&2
    exit 2
fi

here="$(cd "$(dirname "$0")" && pwd)"
eval_id="$1"
dest="$2"

[[ ! -e "$dest" ]] || { echo "$dest already exists; pick a new path" >&2; exit 2; }

TEMPLATE_URL="${DESIGN_SPEC_TEMPLATE_URL:-https://github.com/CarlosSolrac/template-sqlmesh-duckdb}"
PARQUETTOXL_BASE="8ffaa6fb173364321977bf8326ccf95982e26bcf"

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
    GIT_AUTHOR_DATE="2026-10-16T08:00:00+00:00" GIT_COMMITTER_DATE="2026-10-16T08:00:00+00:00" git commit -q -m "$1"
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

build_parquettoxl() {
    git clone -q -b main "$here/fixtures/parquettoxl-8ffaa6f.bundle" "$dest"
    git -C "$dest" remote remove origin
    [[ "$(git -C "$dest" rev-parse HEAD)" == "$PARQUETTOXL_BASE" ]] || die "the bundle's main is not at $PARQUETTOXL_BASE"
}

build_planted_defects() {
    mkdir -p "$dest"
    cp -R "$here/fixtures/planted-defects/." "$dest"
    # safecrlf only silences the warning a core.autocrlf=true user sees for these LF files; what is committed is unchanged.
    (cd "$dest" && git init -q -b main && git -c core.safecrlf=false add -A && commit "tally: daily revenue from an orders CSV")
}

build_resync() {
    git -c core.safecrlf=false clone -q "$TEMPLATE_URL" "$dest" || die "could not clone $TEMPLATE_URL"
    [[ -f "$dest/docs/design.md" ]] || die "eval 4 cannot run yet: $TEMPLATE_URL has no docs/design.md (the template is still being filled), so there is no design to resync"
    git -C "$dest" remote remove origin
    reverse_import
    (cd "$dest" && git -c core.safecrlf=false add -A && commit "Eval 4: ports.py imports from adapters")
}

reverse_import() {  # make the template's ports.py import its sibling adapters module
    local ports dir package
    mapfile -t ports < <(git -C "$dest" ls-files -- ':(glob)**/ports.py')
    [[ ${#ports[@]} -eq 1 ]] || die "eval 4 expects exactly one ports.py in the template, found ${#ports[@]}; update reverse_import in $0"
    dir="$(dirname "${ports[0]}")"
    [[ -f "$dest/$dir/adapters.py" || -d "$dest/$dir/adapters" ]] || die "eval 4 expects adapters.py or adapters/ beside ${ports[0]}; update reverse_import in $0"
    [[ "$dir" != . ]] || die "eval 4 expects ports.py inside a package, found it at the template root; update reverse_import in $0"
    package="${dir##*src/}"
    # Appended at the end, not among the imports: adapters imports ports, and a
    # top-of-file import would fail at run time in one import order (a partially
    # initialised ports). At the end both orders work, so only the design changes.
    printf '\nfrom %s import adapters  # eval 4: the port now depends on an adapter\n' "${package//\//.}" >> "$dest/${ports[0]}"
}

case "$eval_id" in
    1) build_empty ;;
    2) build_small_project ;;
    3) build_parquettoxl ;;
    3b | 5 | 6) build_planted_defects ;;
    4) build_resync ;;
    *) echo "no eval '$eval_id'; expected 1, 2, 3, 4, 5 (also written 3b), or 6" >&2; exit 2 ;;
esac

built=1
echo "eval $eval_id fixture built at $dest"
git -C "$dest" log --oneline -1 2>/dev/null || echo "(no commits)"
