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
files read by AI agents (`CLAUDE.md`, `AGENTS.md`, `.cursorrules`, `.claude/**`, and so on) and the files they
pull in through `@path` imports. File names are checked too.

In the default mode files are read from the git index — the content reviewers see on GitHub — not from the checked-out
working tree, so `.gitattributes` settings (`-diff`, `working-tree-encoding`, filters) and the runner's
filesystem cannot change what is listed or scanned.

### Inputs

| Input | Default | Description |
|---|---|---|
| `files` | all text files tracked by git | Files to scan (newline separated, literal paths). An entry that cannot be read fails the job (`unreadable`) |
| `exclude` | none | Globs to skip (comma separated), e.g. `**/testdata/**`. `*` and `?` stay within one directory, `**` spans directories |
| `report-only` | `odd-space,long-line,base64-blob,private-use,invalid-utf8` | Rules that report without failing the job |
| `working-directory` | `.` | Directory to run in. Only files under it are scanned, so a `.gitattributes` or instruction file above it is not |

When you build `files` from `git diff`, pass literal paths: `git -c core.quotePath=false diff --name-only --diff-filter=d`.
Plain `git diff --name-only` quotes non-ASCII names (`"caf\303\251.py"`) and lists deleted files, and both fail as `unreadable`.

### Example: excluding test data

```yaml
      - uses: kukv/hidden-content-scan@<commit sha> # vX.Y.Z
        with:
          exclude: "**/testdata/**"
```

### Example: strict mode

Files that are not valid UTF-8 are always scanned (decoded with replacement), and by default the invalid
bytes only warn. To fail on them as well, leave `invalid-utf8` out of `report-only`:

```yaml
      - uses: kukv/hidden-content-scan@<commit sha> # vX.Y.Z
        with:
          report-only: "odd-space,long-line,base64-blob,private-use"
```

`report-only: ""` makes every rule fail the job.

## What it detects

| Rule | What it finds | Default |
|---|---|---|
| `bidi` | Bidirectional control characters (Trojan Source) — the rendered order differs from what compiles — and the implicit marks LRM/RLM/ALM | **fails** |
| `zero-width` | Zero-width and invisible characters: every format character (Unicode category Cf), Hangul fillers, CGJ, Mongolian and Khmer invisible marks, U+2028/2029/NEL, and variation selectors that are not a single selector on a CJK ideograph or symbol (the carrier of "emoji smuggling") | **fails** |
| `tag-chars` | Tag characters U+E0000–E007F — **invisible to humans, read by LLMs**; the usual carrier for embedded prompts | **fails** |
| `stray-joiner` | U+FE0F that does not follow an emoji, or U+200D that does not join two emoji | **fails** |
| `mixed-script` | Homoglyphs: Latin mixed with Cyrillic or Greek (any block, including Cyrillic Supplement and Greek Extended) inside a single token, for example `admin` whose `a` is U+0430. Invisible characters cannot split a token | **fails** |
| `hidden-markup` | Markup in AI instruction files that disappears when rendered: HTML comments, `<details>`, `display:none`, `opacity:0`, text colored like the background (also when written with HTML entities or CSS escapes), link reference definitions such as `[//]: # (...)`, `<?...?>`, `<!...>` and CDATA. Fenced code blocks are skipped because they render verbatim | **fails** |
| `diff-hiding` | `.gitattributes` entries that suppress the diff on GitHub: `-diff`, `linguist-generated`, `binary` on a text file, macros that expand to them, and control or unusual space characters that make a line parse differently than it reads | **fails** |
| `unreadable` | A file that was asked for but cannot be read (missing, a directory, or a blob absent from the repository) | **fails** |
| `invalid-utf8` | Bytes that are not valid UTF-8. The file is still scanned | warns |
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
- Detection works from Unicode properties and code point sets rather than an allowlist. Emoji variation
  selectors (U+FE0F) and ZWJ are accepted **only inside real emoji sequences**, and a single variation
  selector only on a CJK ideograph or symbol, so documents containing emoji or kanji variants do not turn the
  check red
- Homoglyph detection only looks at script mixing within a token. Japanese text next to Latin words is
  legitimate and never flagged

## Security notes

- The action never executes content from the checkout: file names do not reach the command line, and Python
  runs isolated (`python3 -I`) so files in the repository cannot shadow its modules.
- That only holds for this step. Do not combine it with steps that build or run pull-request code under
  `pull_request_target` or `workflow_run` with secrets available.

## Development

```bash
./tests/run.sh                      # verify the fixtures are detected as expected
python3 scripts/scan.py --git-index # scan the repository the way the action does
python3 scripts/scan.py <files...>  # scan specific files
```

See [CONTRIBUTING.md](CONTRIBUTING.md) for how to add a rule and what CI checks.

## License

[MIT](LICENSE)
