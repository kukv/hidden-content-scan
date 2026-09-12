# Contributing

Thanks for taking the time to improve hidden-content-scan.

## Getting started

The scanner is a single Python file that runs on the **standard library only**
(`scripts/scan.py`). Nothing needs to be installed beyond `python3` and `bash`.

```bash
./tests/run.sh                      # verify the fixtures are detected as expected
python3 scripts/scan.py <files...>  # run it locally
```

Keep the standard-library-only rule. A scanner that pulls in dependencies becomes
the supply-chain weak point it is meant to guard against.

## Adding or changing a rule

1. Add a fixture under `tests/fixtures/` that contains the pattern to detect.
2. Add an `expect <exit> <rule> <files...>` line to `tests/run.sh`.
3. Document the rule in the table in `README.md` and `README.ja.md`.
4. If the rule should warn rather than fail the job, add it to the `report-only`
   default in `action.yml` and say so in both READMEs.

Fixtures are intentionally dirty, so the `self-check` job in `.github/workflows/ci.yml`
excludes `tests/fixtures/*`. Keep new fixtures inside that directory.

False negatives matter more than false positives here: a pattern that a human
reviewer cannot see and the scanner does not report is the failure this action
exists to prevent. Still, a rule that fires on legitimate documents (emoji, Japanese
text next to Latin words) gets ignored in practice, so cover both sides with fixtures.

## Pull requests

- CI runs on every pull request: `ci.yml` (the fixture tests plus a self-check that
  applies the action to this repository) and `security.yml` (gitleaks, osv-scanner,
  zizmor, actionlint). All of them must pass.
- Pin any GitHub Action you add to a full commit SHA with a `# vX.Y.Z` comment, and
  pin Docker images by digest. Renovate follows them through the `# renovate:` annotations.
- Commit messages use a `feat:` / `fix:` / `docs:` / `chore:` prefix.
- Label the pull request so it lands in the right section of the release notes —
  see the categories in `.github/release.yaml` (`Kind: Feature`, `Kind: Bug Fix`,
  `Kind: Enhancement`, `Impact: Breaking`, `Kind: Dependencies`).
- Review by the maintainer (`.github/CODEOWNERS`) is required before merge.

## Use of AI

AI assistance is fine. Submitting what an AI produced without understanding it is not.

Generating a submission takes seconds; verifying one takes a person's time. Sending
unverified output moves that cost onto the maintainer and takes time away from the review
this project actually needs.

Before you open an issue or a pull request, you are expected to have read the output,
verified it against this repository, and be able to explain and defend it. You are the
author of what you submit, whatever tool helped you write it.

Issues and pull requests that appear to be unreviewed AI output — invented rules, files
or inputs that do not exist, a diff that does not follow from the description, boilerplate
that does not engage with this project — are **closed without notice and without
individual explanation**. That judgment is the maintainer's, and there is no appeal
process; you are welcome to open a new issue or pull request that shows your own reasoning.

Closing one does not mean the underlying point was worthless. If a closed issue or pull
request contains something useful, the maintainer may take it up — as an issue raised by
the maintainer, or by merging or rewriting the change — without notice and without credit
to the original submitter. Anything you submit is already licensed under the
[MIT License](LICENSE) as stated above, and opening an issue or pull request here means
you accept this handling.

## Reporting problems

- A missed detection or any other security-relevant issue: see [SECURITY.md](SECURITY.md).
- Anything else: open an issue with the file or snippet that reproduces it.

By contributing you agree that your contributions are licensed under the
[MIT License](LICENSE).
