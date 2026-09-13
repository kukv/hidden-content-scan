**A pull request that does not fill this in is closed without review.** See
[CONTRIBUTING.md](https://github.com/kukv/hidden-content-scan/blob/main/CONTRIBUTING.md) before
opening one. Commits use a `feat:` / `fix:` / `docs:` / `chore:` prefix; CI must pass.

## What and why

<!-- What changes, and why. "Why" is required — a diff without a reason is closed. -->

## Verification

<!-- The exact commands you ran (e.g. `./tests/run.sh`) and what they printed. "I tested it" is
     not enough on its own. -->

## Scope

<!-- `scripts/scan.py` runs on the standard library only — a dependency is not an option here.
     If this adds or changes a rule, confirm you added a fixture under `tests/fixtures/`, an
     `expect` line in `tests/run.sh`, the rule row in both `README.md` and `README.ja.md`, and —
     if it warns rather than fails — the `report-only` default in `action.yml`. Cover the rule
     from both sides: what it must catch, and the legitimate content it must not fire on.
     If you touched a workflow, confirm any new or changed action is pinned to a full commit SHA
     with a `# vX.Y.Z` comment. -->

## Release notes label

<!-- Which label from .github/release.yaml applies to this change, so the maintainer can attach
     it: Kind: Feature, Kind: Bug Fix, Kind: Enhancement, Impact: Breaking, or Kind: Dependencies. -->

## AI use (verified?)

<!-- If AI assisted this submission, confirm per
     [Use of AI](https://github.com/kukv/hidden-content-scan/blob/main/CONTRIBUTING.md#use-of-ai)
     that you've read, verified and can defend the output. -->
