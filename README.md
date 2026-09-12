# hidden-content-scan

[日本語](README.ja.md)

A GitHub Action that detects content **a human reviewer cannot see**.

Its purpose is to stop hidden implementation code and hidden prompts — the kind that slip through
because no amount of staring at a diff reveals them.

## Usage

```yaml
      - uses: kukv/hidden-content-scan@<commit sha> # vX.Y.Z
```

By default it scans **every text file tracked by git** (binaries are skipped), including instruction
files read by AI agents (`CLAUDE.md`, `AGENTS.md`, `.cursorrules`, `.claude/**`, and so on).

### Inputs

| Input | Default | Description |
|---|---|---|
| `files` | all text files tracked by git | Files to scan (newline separated) |
| `exclude` | none | Globs to skip (comma separated), e.g. `**/testdata/**` |
| `report-only` | `odd-space,long-line,base64-blob,private-use` | Rules that report without failing the job |
| `working-directory` | `.` | Directory to run in |

### Example: excluding test data

```yaml
      - uses: kukv/hidden-content-scan@<commit sha> # vX.Y.Z
        with:
          exclude: "**/testdata/**"
```

## What it detects

| Rule | What it finds | Default |
|---|---|---|
| `bidi` | Bidirectional control characters (Trojan Source) — the rendered order differs from what compiles | **fails** |
| `zero-width` | Zero-width and invisible characters (U+200B/200C/FEFF/00AD/180E, Hangul filler, invisible operators, interlinear annotation) | **fails** |
| `tag-chars` | Tag characters U+E0000–E007F — **invisible to humans, read by LLMs**; the usual carrier for embedded prompts | **fails** |
| `stray-joiner` | U+FE0F / U+200D attached to something that is not an emoji | **fails** |
| `mixed-script` | Homoglyphs: Latin mixed with Cyrillic or Greek inside a single token (for example `admin` whose `a` is U+0430) | **fails** |
| `hidden-markup` | Markup in AI instruction files that disappears when rendered: HTML comments, `<details>`, `display:none`, text colored like the background | **fails** |
| `diff-hiding` | `.gitattributes` entries that suppress the diff on GitHub: `-diff`, `linguist-generated`, `binary` on a text file | **fails** |
| `private-use` | Private use area characters — legitimately used by Nerd Font icons | warns |
| `odd-space` | Unusual whitespace such as NBSP | warns |
| `long-line` | Lines over 2000 characters, which GitHub does not expand by default | warns |
| `base64-blob` | Base64-looking runs of 500 characters or more | warns |

Use the `report-only` input to move rules between failing and warning.

## What it does not detect

- Code that is **visible but misleading** (confusing names, subtle logic) — that is what review itself is for
- The contents of third-party dependencies — that belongs to SCA (osv-scanner and friends)
- Code baked into build artifacts — keep the source under review instead

## Design

- Runs on the **standard library only** (`scripts/scan.py`). A scanner that pulls in dependencies becomes
  the supply-chain weak point it is meant to guard against
- Detection works from code point sets rather than an allowlist. Emoji variation selectors (U+FE0F) and
  ZWJ are accepted **only when the preceding code point is an emoji**, so documents containing emoji do
  not turn the check red
- Homoglyph detection only looks at script mixing within a token. Japanese text next to Latin words is
  legitimate and never flagged

## Development

```bash
./tests/run.sh                      # verify the fixtures are detected as expected
python3 scripts/scan.py <files...>  # run it locally
```
