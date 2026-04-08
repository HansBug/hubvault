#!/usr/bin/env bash
set -euo pipefail

TMPDIR="$(mktemp -d)"
REPO="$TMPDIR/repo"
MODEL="$TMPDIR/model.bin"
README_FILE="$TMPDIR/README.md"

printf 'weights-v1' > "$MODEL"
printf '# CLI demo\n' > "$README_FILE"

{
    hubvault init "$REPO"
    hubvault -C "$REPO" commit -m "add weights" --add "artifacts/model.bin=$MODEL"
    hubvault -C "$REPO" branch feature
    hubvault -C "$REPO" commit -r feature -m "add readme" --add "README.md=$README_FILE"
    hubvault -C "$REPO" merge feature --target main
    hubvault -C "$REPO" log --oneline
    hubvault -C "$REPO" ls-tree -r
    hubvault -C "$REPO" verify
} | sed "s|$TMPDIR|<tmp>|g"
