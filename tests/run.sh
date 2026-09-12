#!/usr/bin/env bash
# Verify the fixtures are detected as expected. Shell + python only, to avoid adding dependencies.
set -euo pipefail
cd "$(dirname "$0")/.."

fail=0
expect() { # expect <expected exit> <expected rule|-> <files...>
  local want_exit=$1 want_rule=$2; shift 2
  local out rc=0
  out=$(python3 scripts/scan.py "$@" 2>&1) || rc=$?
  if [ "$rc" != "$want_exit" ]; then
    echo "NG: $* -> exit $rc (expected $want_exit)"; echo "$out"; fail=1; return
  fi
  if [ "$want_rule" != "-" ] && ! grep -q "\[$want_rule\]" <<<"$out"; then
    echo "NG: $* -> rule $want_rule was not reported"; echo "$out"; fail=1; return
  fi
  echo "OK: $* (${want_rule})"
}

expect 1 bidi          tests/fixtures/bidi.ts
expect 1 zero-width    tests/fixtures/zero_width.py
expect 1 tag-chars     tests/fixtures/tag_chars.md
expect 1 mixed-script  tests/fixtures/homoglyph.js
expect 1 hidden-markup tests/fixtures/CLAUDE.md
expect 0 -             tests/fixtures/clean_emoji.md
expect 0 -             tests/fixtures/clean_japanese.md

# .gitattributes is matched by path name, so check it from a temporary directory
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT
cp tests/fixtures/gitattributes_sample "$tmp/.gitattributes"
script=$PWD/scripts/scan.py
out=$(cd "$tmp" && python3 "$script" .gitattributes 2>&1) && rc=0 || rc=$?
if [ "$rc" = 1 ] && grep -q '\[diff-hiding\]' <<<"$out"; then
  echo "OK: .gitattributes (diff-hiding)"
else
  echo "NG: diff-hiding was not reported for .gitattributes"; echo "$out"; fail=1
fi

# report-only rules must not fail the run
long=$(mktemp); python3 -c "print('a'*3000)" > "$long"
if python3 scripts/scan.py "$long" >/dev/null; then echo "OK: long-line only warns"; else echo "NG: long-line failed the run"; fail=1; fi
rm -f "$long"

exit $fail
