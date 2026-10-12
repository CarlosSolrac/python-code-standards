#!/usr/bin/env bash
#
# build-fixture.sh -- build a nightshift eval fixture as a fresh git repository.
#
#   nightshift/evals/build-fixture.sh <fixture> <dest>
#
# <fixture> names a directory under fixtures/; <dest> must not exist yet. Build it
# outside this repository, in a folder of its own: nightshift puts its worktrees
# next to the repository, in <dest>.nightshift/.
#
# The repository is assembled from:
#   fixtures/base/                 the statskit project, committed on main
#   fixtures/<fixture>/main/       files added to that first commit (TODO.md)
#   fixtures/<fixture>/branch-X/   files committed on top of main as nightshift/X
#   fixtures/<fixture>/nightshift/ copied to .nightshift/, which is git-excluded,
#                                  as a night already in progress would leave it
#
# Author, committer and dates are fixed, so the same fixture gives the same commit
# SHAs on every build; graders compare against the SHAs printed at the end. No
# remote is added.

set -euo pipefail

if [[ $# -ne 2 ]]; then
    echo "usage: $0 <fixture> <dest>" >&2
    exit 2
fi

fixtures="$(cd "$(dirname "$0")/fixtures" && pwd)"
fixture="$fixtures/$1"
dest="$2"

[[ -d "$fixture" && "$1" != base ]] || { echo "no fixture named '$1' in $fixtures" >&2; exit 2; }
[[ ! -e "$dest" ]] || { echo "$dest already exists; pick a new path" >&2; exit 2; }

export GIT_AUTHOR_NAME="Fixture" GIT_AUTHOR_EMAIL="fixture@example.invalid"
export GIT_COMMITTER_NAME="Fixture" GIT_COMMITTER_EMAIL="fixture@example.invalid"

commit() {  # commit <date> <message>
    GIT_AUTHOR_DATE="$1" GIT_COMMITTER_DATE="$1" git commit -q -m "$2"
}

mkdir -p "$dest"
cp -R "$fixtures/base/." "$dest"
[[ -d "$fixture/main" ]] && cp -R "$fixture/main/." "$dest"
cd "$dest"
git init -q -b main
git add -A
commit "2026-10-07T20:00:00+00:00" "Initial statskit project"

for branch_dir in "$fixture"/branch-*/; do
    [[ -d "$branch_dir" ]] || continue
    name="$(basename "$branch_dir")"
    git switch -q -c "nightshift/${name#branch-}"
    cp -R "$branch_dir." .
    git add -A
    commit "2026-10-07T21:40:00+00:00" "nightshift: ${name#branch-}"
    git switch -q main
done

if [[ -d "$fixture/nightshift" ]]; then
    mkdir .nightshift
    cp -R "$fixture/nightshift/." .nightshift
    echo ".nightshift/" >> .git/info/exclude
fi

git for-each-ref --format='%(objectname) %(refname:short)' refs/heads
