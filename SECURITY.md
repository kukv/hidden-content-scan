# Security Policy

## Supported versions

Only the latest release is supported. Users are expected to pin this action to a
commit SHA (`uses: kukv/hidden-content-scan@<commit sha> # vX.Y.Z`) and to update
that pin when a new release is published; fixes are not backported to older tags.

## Reporting a vulnerability

Report privately through GitHub: open the **Security** tab of this repository and
choose **Report a vulnerability**. Please do not open a public issue, and do not
attach a working payload to anything public.

Include the file or snippet that reproduces the problem, the rules involved, and
the version (commit SHA) you ran.

## What counts as a security issue

- **A bypass of a failing rule.** Content that a human reviewer cannot see —
  invisible Unicode, homoglyphs, markup that disappears when rendered — which the
  scanner does not report. This is the failure mode the action exists to prevent.
- **Anything that lets scanned content affect the runner**, for example a crafted
  file name or file content that causes the action to execute it.

Not a security issue:

- False positives, including on rules that only warn. Open an ordinary issue.
- Content the README lists under "What it does not detect" (visible but misleading
  code, third-party dependencies, build artifacts).

## Handling

Reports are acknowledged and triaged by the maintainer. Once a fix is released, the
advisory is published with credit to the reporter unless anonymity is requested.
