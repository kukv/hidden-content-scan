#!/usr/bin/env python3
"""Detect content a human reviewer cannot see.

The target is anything that stares back invisibly from a diff:
  - Invisible / formatting Unicode (Trojan Source, zero-width, tag characters only LLMs read)
  - Homoglyphs (Cyrillic or Greek letters disguised as Latin)
  - Markup in AI instruction files that disappears when rendered
  - .gitattributes entries that suppress the diff on GitHub

Runs on the standard library alone: a scanner with dependencies becomes the supply-chain
weak point it is meant to guard against.
"""
from __future__ import annotations

import argparse
import html
import os
import posixpath
import re
import subprocess
import sys
import unicodedata
from dataclasses import dataclass

# --- Invisible / formatting characters -------------------------------------
# Embedding/override/isolate controls plus the implicit marks LRM, RLM and ALM
BIDI = set(range(0x202A, 0x202F)) | set(range(0x2066, 0x206A)) | {0x200E, 0x200F, 0x061C}
# Default-ignorable letters and marks that are not category Cf, plus line/paragraph
# separators that some renderers draw as nothing (and JavaScript treats as a line break)
ZERO_WIDTH = {
    0x200B, 0x200C, 0xFEFF, 0x00AD, 0x180E, 0x3164, 0x115F, 0x1160, 0xFFA0,
    0x034F, 0x17B4, 0x17B5, 0x180B, 0x180C, 0x180D, 0x180F, 0x2028, 0x2029, 0x0085,
}
INVISIBLE_MATH = set(range(0x2060, 0x2065))
ANNOTATION = set(range(0xFFF9, 0xFFFC))
TAG_CHARS = set(range(0xE0000, 0xE0080))
PRIVATE_USE = set(range(0xE000, 0xF900)) | set(range(0xF0000, 0x10FFFE))
ODD_SPACE = {0x00A0, 0x202F, 0x205F, 0x3000, 0x2800} | set(range(0x2000, 0x200B))
EMOJI_JOINERS = {0xFE0F, 0x200D}
# U+FE0F is judged together with ZWJ as an emoji joiner
VARIATION_SELECTORS = set(range(0xFE00, 0xFE0F)) | set(range(0xE0100, 0xE01F0))

# --- AI instruction files ---------------------------------------------------
# Compared case-insensitively: case-insensitive filesystems load claude.md as CLAUDE.md
AI_FILENAMES = {
    "claude.md", "claude.local.md", "agents.md", "agents.override.md", "agent.md", "gemini.md",
    ".cursorrules", ".clinerules", ".windsurfrules", "copilot-instructions.md",
}
AI_DIR_MARKERS = (
    "/.claude/", "/.cursor/", "/.clinerules/", "/.windsurf/", "/.roo/", "/.kiro/", "/.junie/",
    "/.github/instructions/", "/.github/prompts/", "/.github/agents/", "/.github/chatmodes/",
)
# `@path` imports in instruction files (Claude Code memory imports), followed this deep
AI_IMPORT = re.compile(r"(?<![\w@])@((?:\.{1,2}/)?[\w.\-/]*[\w/])")
AI_IMPORT_DEPTH = 5

HIDDEN_MARKUP = [
    (re.compile(r"<!--"), "HTML comment (invisible once rendered)"),
    (re.compile(r"<details\b", re.I), "collapsed behind <details>"),
    (re.compile(r"display\s*:\s*none", re.I), "display:none"),
    (re.compile(r"visibility\s*:\s*hidden", re.I), "visibility:hidden"),
    (re.compile(r"font-size\s*:\s*0", re.I), "font-size:0"),
    (re.compile(r"opacity\s*:\s*(?:0+(?:\.0*)?|\.0+)(?![.\d])", re.I), "opacity:0"),
    (re.compile(r"color\s*:\s*(#f{3}\b|#f{6}\b|white|transparent)", re.I), "text colored like the background"),
    (re.compile(r"^ {0,3}\[[^\]\n]+\]:", re.M), "link reference definition (not rendered)"),
    (re.compile(r"<\?"), "processing instruction (not rendered)"),
    (re.compile(r"<![A-Za-z\[]"), "declaration or CDATA section (not rendered)"),
]
# Fenced code blocks render their contents verbatim, so markup inside them is visible
CODE_FENCE = re.compile(r"^ {0,3}(`{3,}|~{3,})")
CSS_ESCAPE = re.compile(r"\\([0-9a-fA-F]{1,6})[ \t\r\n\f]?|\\(.)", re.S)

# Entries that suppress the diff. `binary` is normal on real binaries such as images
# and fonts, so it is only a problem when applied to something that could be text.
BINARY_EXTENSIONS = {
    "png", "jpg", "jpeg", "gif", "ico", "icns", "bmp", "webp", "avif", "svgz",
    "woff", "woff2", "ttf", "otf", "eot", "pdf", "zip", "gz", "tgz", "bz2", "xz",
    "7z", "rar", "jar", "war", "ear", "class", "so", "dylib", "dll", "exe", "bin",
    "wasm", "mp3", "mp4", "mov", "avi", "webm", "ogg", "wav", "keystore", "jks",
    "p12", "pfx", "der", "db", "sqlite", "parquet", "xlsx", "docx", "pptx",
}
# The pattern must be literally `*.<ext>` or a plain file name for the allowance to apply
LITERAL_BINARY_NAME = re.compile(r"\*?[^*?\[\\]*\.([A-Za-z0-9]+)")
ATTR_SEPARATORS = re.compile(r"[ \t\r]+")

# Rules that only warn by default: legitimate uses are common in real repositories
# (private-use covers Nerd Font icons, invalid-utf8 covers files in legacy encodings)
DEFAULT_REPORT_ONLY = {"odd-space", "long-line", "base64-blob", "private-use", "invalid-utf8"}

LONG_LINE = 2000
BASE64_BLOB = re.compile(r"[A-Za-z0-9+/]{500,}={0,2}")
BINARY_SNIFF = 8000  # git's heuristic: a NUL within the first 8000 bytes means binary


@dataclass
class Finding:
    rule: str
    path: str
    line: int  # 0 when the finding is about the file itself (its name, or reading it)
    col: int
    detail: str


@dataclass
class Source:
    path: str  # path shown in reports and used for classification
    match_path: str  # path the exclude globs are matched against
    data: bytes | None
    error: str | None = None


def _script_of(ch: str) -> str | None:
    if ch.isascii():
        return "Latin" if ch.isalpha() else None
    name = unicodedata.name(ch, "")
    if name.startswith("CYRILLIC"):
        return "Cyrillic"
    if name.startswith(("GREEK", "COPTIC")):
        return "Greek"
    return None


def _emoji_ish(cp: int) -> bool:
    return (
        0x1F000 <= cp <= 0x1FAFF
        or 0x2600 <= cp <= 0x27BF
        or cp in (0x2B50, 0x2B55, 0x00A9, 0x00AE, 0x203C, 0x2049)
    )


def _variation_allowed(prev: str, cp: int) -> bool:
    """A single selector right after a base that defines variants is legitimate."""
    if not prev or ord(prev) in VARIATION_SELECTORS or ord(prev) in EMOJI_JOINERS:
        return False
    cjk = unicodedata.name(prev, "").startswith("CJK ")
    if cp >= 0xE0100:  # ideographic variation sequences (kanji variants)
        return cjk
    return cjk or unicodedata.category(prev).startswith("S")


def _ignorable(cp: int) -> bool:
    return (
        cp in BIDI or cp in ZERO_WIDTH or cp in INVISIBLE_MATH or cp in ANNOTATION
        or cp in TAG_CHARS or cp in VARIATION_SELECTORS or cp in EMOJI_JOINERS
        or unicodedata.category(chr(cp)) == "Cf"
    )


def _is_ai_instruction_file(path: str) -> bool:
    path = path.replace("\\", "/").removeprefix("./").lower()
    name = path.rsplit("/", 1)[-1]
    if name in AI_FILENAMES or name.endswith(".mdc"):
        return True
    return any(marker in "/" + path for marker in AI_DIR_MARKERS)


def _name_of(ch: str) -> str:
    return unicodedata.name(ch, "UNNAMED")


def _scan_chars(path: str, lineno: int, line: str, out: list[Finding]) -> None:
    """Code point and homoglyph rules, shared by file contents and file names."""
    for col, ch in enumerate(line, 1):
        cp = ord(ch)
        prev = line[col - 2] if col >= 2 else ""
        if cp in BIDI:
            out.append(Finding("bidi", path, lineno, col, f"U+{cp:04X} {_name_of(ch)}"))
        elif cp in TAG_CHARS:
            out.append(Finding("tag-chars", path, lineno, col, f"U+{cp:04X} {_name_of(ch)}"))
        elif cp in EMOJI_JOINERS:
            # FE0F must sit on an emoji; ZWJ must join two emoji (the left one may carry FE0F)
            nxt = line[col] if col < len(line) else ""
            base = line[col - 3] if prev == "\ufe0f" and col >= 3 else prev
            if cp == 0xFE0F:
                ok = bool(prev) and _emoji_ish(ord(prev))
            else:
                ok = bool(base) and bool(nxt) and _emoji_ish(ord(base)) and _emoji_ish(ord(nxt))
            if not ok:
                out.append(Finding("stray-joiner", path, lineno, col, f"U+{cp:04X} attached to a non-emoji"))
        elif cp in VARIATION_SELECTORS:
            if not _variation_allowed(prev, cp):
                out.append(Finding("zero-width", path, lineno, col, f"U+{cp:04X} {_name_of(ch)}"))
        elif cp in ZERO_WIDTH or cp in INVISIBLE_MATH or cp in ANNOTATION:
            out.append(Finding("zero-width", path, lineno, col, f"U+{cp:04X} {_name_of(ch)}"))
        elif cp in PRIVATE_USE:
            out.append(Finding("private-use", path, lineno, col, f"U+{cp:04X} private use area"))
        elif cp in ODD_SPACE:
            out.append(Finding("odd-space", path, lineno, col, f"U+{cp:04X} {_name_of(ch)}"))
        elif unicodedata.category(ch) == "Cf":
            out.append(Finding("zero-width", path, lineno, col, f"U+{cp:04X} {_name_of(ch)}"))

    # Tokenize with invisible characters removed, so they cannot split a mixed token
    kept = [(col, ch) for col, ch in enumerate(line, 1) if not _ignorable(ord(ch))]
    visible = "".join(ch for _, ch in kept)
    for match in re.finditer(r"\w+", visible):
        scripts = {s for s in (_script_of(c) for c in match.group()) if s}
        if len(scripts) > 1:
            out.append(Finding("mixed-script", path, lineno, kept[match.start()][0],
                               f"{match.group()} mixes {'+'.join(sorted(scripts))}"))


def _css_unescape(text: str) -> str:
    def repl(m: re.Match[str]) -> str:
        if m.group(1) is None:
            return m.group(2)
        cp = int(m.group(1), 16)
        return chr(cp) if 0 < cp <= 0x10FFFF and not 0xD800 <= cp <= 0xDFFF else "\ufffd"
    return CSS_ESCAPE.sub(repl, text)


def _mask_code_fences(text: str) -> str:
    """Blank out fenced code blocks, keeping offsets so line and column numbers stay right."""
    lines, fence = text.split("\n"), ""
    for i, line in enumerate(lines):
        m = CODE_FENCE.match(line)
        if not fence:
            if m and not (m.group(1)[0] == "`" and "`" in line[m.end():]):
                fence = m.group(1)
                lines[i] = " " * len(line)
            continue
        if m and m.group(1)[0] == fence[0] and len(m.group(1)) >= len(fence) and not line[m.end():].strip():
            fence = ""
        lines[i] = " " * len(line)
    return "\n".join(lines)


def _scan_markup(path: str, text: str) -> list[Finding]:
    found: dict[tuple[int, str], Finding] = {}
    text = _mask_code_fences(text)
    # Entity- or escape-encoded CSS still hides text, so match the decoded text as well
    for candidate in dict.fromkeys((text, html.unescape(_css_unescape(text)))):
        for pattern, label in HIDDEN_MARKUP:
            for m in pattern.finditer(candidate):
                lineno = candidate.count("\n", 0, m.start()) + 1
                col = m.start() - (candidate.rfind("\n", 0, m.start()) + 1) + 1
                found.setdefault((lineno, label), Finding("hidden-markup", path, lineno, col, label))
    return sorted(found.values(), key=lambda f: (f.line, f.col))


def scan_text(path: str, text: str, ai_file: bool | None = None) -> list[Finding]:
    out: list[Finding] = []
    if ai_file is None:
        ai_file = _is_ai_instruction_file(path)
    gitattributes = path == ".gitattributes" or path.endswith("/.gitattributes")

    # Split on LF only: other separators (U+2028, NEL, FF ...) must stay visible to the rules
    for lineno, line in enumerate(text.split("\n"), 1):
        line = line.removesuffix("\r")
        _scan_chars(path, lineno, line, out)
        if len(line) > LONG_LINE:
            out.append(Finding("long-line", path, lineno, 1, f"{len(line)} characters (diff not expanded by default)"))
        if BASE64_BLOB.search(line):
            out.append(Finding("base64-blob", path, lineno, 1, "long base64-looking run"))

    if ai_file:
        out.extend(_scan_markup(path, text))
    if gitattributes:
        out.extend(_scan_gitattributes(path, text))
    return out


def _split_attr_line(line: str) -> tuple[str, list[str]]:
    """Split one .gitattributes line the way git does: a pattern (optionally C-quoted), then attributes."""
    if line.startswith('"'):
        i, pattern = 1, ""
        while i < len(line) and line[i] != '"':
            if line[i] == "\\" and i + 1 < len(line):
                i += 1
            pattern += line[i]
            i += 1
        rest = line[i + 1:]
    else:
        parts = ATTR_SEPARATORS.split(line, maxsplit=1)
        pattern, rest = parts[0], parts[1] if len(parts) > 1 else ""
    return pattern, [a for a in ATTR_SEPARATORS.split(rest) if a]


def _suppresses(attr: str, macros: set[str]) -> bool:
    if attr in ("-diff", "binary") or attr in macros:
        return True
    name, _, value = attr.partition("=")
    return name == "linguist-generated" and value.lower() != "false"


def _scan_gitattributes(path: str, text: str) -> list[Finding]:
    out: list[Finding] = []
    entries: list[tuple[int, str, list[str]]] = []
    for lineno, line in enumerate(text.split("\n"), 1):
        for col, ch in enumerate(line, 1):
            cat = unicodedata.category(ch)
            if (cat == "Cc" and ch not in "\t\r") or (cat == "Zs" and ch != " ") or cat == "Zl" or cat == "Zp":
                out.append(Finding("diff-hiding", path, lineno, col,
                                   f"U+{ord(ch):04X} makes this line parse differently than it reads"))
        stripped = line.strip(" \t\r")
        if not stripped or stripped.startswith("#"):
            continue
        entries.append((lineno, *_split_attr_line(stripped)))

    # User macros (`[attr]name ...`) that expand to a suppressor hide diffs wherever they are used
    macros: set[str] = set()
    for _, pattern, attrs in entries:
        if pattern.startswith("[attr]") and any(_suppresses(a, macros) for a in attrs):
            macros.add(pattern.removeprefix("[attr]"))

    for lineno, pattern, attrs in entries:
        hiding = [a for a in attrs if _suppresses(a, macros)]
        if not hiding:
            continue
        literal = LITERAL_BINARY_NAME.fullmatch(pattern.rsplit("/", 1)[-1])
        if all(a == "binary" for a in hiding) and literal and literal.group(1).lower() in BINARY_EXTENSIONS:
            continue  # binary on images and fonts is legitimate
        out.append(Finding("diff-hiding", path, lineno, 1,
                           f"{pattern} will not be shown as a diff on GitHub ({' '.join(hiding)})"))
    return out


def _decode(path: str, data: bytes) -> tuple[str, list[Finding]]:
    """Decode leniently so that one bad byte cannot hide the rest of the file from the rules."""
    try:
        return data.decode("utf-8"), []
    except UnicodeDecodeError as e:
        lineno = data.count(b"\n", 0, e.start) + 1
        col = len(data[data.rfind(b"\n", 0, e.start) + 1:e.start].decode("utf-8", "replace")) + 1
        return data.decode("utf-8", "replace"), [Finding("invalid-utf8", path, lineno, col, "not valid UTF-8 (scanned as decoded with replacement)")]


def _git(*args: str) -> bytes:
    return subprocess.run(["git", *args], check=True, stdout=subprocess.PIPE).stdout


def index_sources() -> list[Source]:
    """Tracked regular files, read from the index rather than the working tree.

    The index holds what reviewers see. Attributes (-diff, working-tree-encoding, filters) and
    the runner's filesystem (case folding) cannot change what gets listed or scanned.
    """
    prefix = os.fsdecode(_git("rev-parse", "--show-prefix").rstrip(b"\n"))
    entries: list[tuple[str, str]] = []
    for record in _git("ls-files", "-z", "--stage").split(b"\0"):
        if not record:
            continue
        meta, _, raw_path = record.partition(b"\t")
        mode, oid, _stage = meta.decode().split()
        if mode in ("100644", "100755"):  # skip symlinks and submodules, as git grep does
            entries.append((oid, os.fsdecode(raw_path)))
    if not entries:
        return []

    batch = subprocess.run(["git", "cat-file", "--batch"], check=True, stdout=subprocess.PIPE,
                           input="".join(oid + "\n" for oid, _ in entries).encode()).stdout
    sources: list[Source] = []
    pos = 0
    for oid, rel in entries:
        end = batch.index(b"\n", pos)
        header = batch[pos:end].split()
        pos = end + 1
        data: bytes | None = None
        if len(header) == 3:
            size = int(header[2])
            data = batch[pos:pos + size]
            pos += size + 1
        sources.append(Source(prefix + rel, rel, data, None if data is not None else "blob missing from the repository"))
    return sources


def file_source(path: str) -> Source:
    try:
        with open(path, "rb") as f:
            return Source(path, path, f.read())
    except OSError as e:
        return Source(path, path, None, f"cannot be read ({e.strerror or e.__class__.__name__})")


def _glob(pattern: str) -> re.Pattern[str]:
    """gitignore-style glob: `*` and `?` stay within a path segment, `**` spans directories."""
    regex, i = "", 0
    while i < len(pattern):
        if pattern.startswith("**/", i):
            regex, i = regex + "(?:.*/)?", i + 3
        elif pattern.startswith("**", i):
            regex, i = regex + ".*", i + 2
        elif pattern[i] == "*":
            regex, i = regex + "[^/]*", i + 1
        elif pattern[i] == "?":
            regex, i = regex + "[^/]", i + 1
        elif pattern[i] == "[" and "]" in pattern[i + 2:]:
            end = pattern.index("]", i + 2)
            body = pattern[i + 1:end]
            negate = body[:1] in ("!", "^")
            regex += "[" + ("^" if negate else "") + re.escape(body[1:] if negate else body) + "]"
            i = end + 1
        else:
            regex, i = regex + re.escape(pattern[i]), i + 1
    return re.compile(regex, re.S)


def _ai_files(texts: dict[str, str]) -> set[str]:
    """Instruction files by name, plus whatever they pull in through `@path` imports."""
    ai = {p for p in texts if _is_ai_instruction_file(p)}
    frontier = set(ai)
    for _ in range(AI_IMPORT_DEPTH):
        found = set()
        for p in frontier:
            for ref in AI_IMPORT.findall(texts[p]):
                target = posixpath.normpath(posixpath.join(posixpath.dirname(p), ref))
                if target in texts and target not in ai:
                    found.add(target)
        ai |= found
        frontier = found
    return ai


def _visible(text: str) -> str:
    """Escape what a terminal would hide or reorder, and line breaks that would start a new line."""
    return "".join(c if c.isprintable() or c == " " else f"\\u{ord(c):04x}" for c in text)


def _command_data(text: str) -> str:
    return text.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")


def _command_property(text: str) -> str:
    return _command_data(text).replace(":", "%3A").replace(",", "%2C")


def main(argv: list[str]) -> int:
    sys.stdout.reconfigure(errors="backslashreplace")
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("files", nargs="*")
    parser.add_argument("--git-index", action="store_true",
                        help="scan every tracked regular file as stored in the git index")
    parser.add_argument("--files-from", metavar="FILE",
                        help="read NUL-separated paths to scan from FILE")
    parser.add_argument("--report-only", default=",".join(sorted(DEFAULT_REPORT_ONLY)),
                        help="rules that report without failing (comma separated)")
    parser.add_argument("--exclude", default="", help="globs to skip (comma separated)")
    parser.add_argument("--github-annotations", action="store_true",
                        help="also emit GitHub Actions annotations")
    args = parser.parse_args(argv)

    report_only = {r.strip() for r in args.report_only.split(",") if r.strip()}
    excludes = [_glob(g.strip()) for g in args.exclude.split(",") if g.strip()]

    paths = list(args.files)
    if args.files_from:
        with open(args.files_from, "rb") as f:
            paths += [os.fsdecode(p) for p in f.read().split(b"\0") if p]
    try:
        sources = (index_sources() if args.git_index else []) + [file_source(p) for p in paths]
    except subprocess.CalledProcessError as e:
        print(f"ERROR git {' '.join(e.cmd[1:])} failed (exit {e.returncode})", file=sys.stderr)
        return 2
    sources = [s for s in sources if not any(g.fullmatch(s.match_path) for g in excludes)]

    findings: list[Finding] = []
    texts: dict[str, str] = {}
    for src in sources:
        name_hits: list[Finding] = []
        _scan_chars(src.path, 0, src.path, name_hits)
        findings.extend(Finding(f.rule, f.path, 0, 0, f"{f.detail} in the file name") for f in name_hits)
        if src.data is None:
            findings.append(Finding("unreadable", src.path, 0, 0, src.error or "cannot be read"))
        elif b"\0" not in src.data[:BINARY_SNIFF]:
            text, decode_hits = _decode(src.path, src.data)
            findings.extend(decode_hits)
            texts[posixpath.normpath(src.path.replace("\\", "/"))] = text

    ai = _ai_files(texts)
    for path, text in texts.items():
        findings.extend(scan_text(path, text, ai_file=path in ai))

    blocking = [f for f in findings if f.rule not in report_only]
    warnings = [f for f in findings if f.rule in report_only]

    for label, group in (("ERROR", blocking), ("WARN", warnings)):
        for f in group:
            where = f"{_visible(f.path)}:{f.line}:{f.col}" if f.line else _visible(f.path)
            print(f"{label} {where}: [{f.rule}] {_visible(f.detail)}")
            if args.github_annotations:
                kind = "error" if label == "ERROR" else "warning"
                props = f"file={_command_property(f.path)}" + (f",line={f.line},col={f.col}" if f.line else "")
                print(f"::{kind} {props}::{_command_data(f'[{f.rule}] {f.detail}')}")

    print(f"\nscanned {len(sources)} files: {len(blocking)} error(s), {len(warnings)} warning(s)")
    return 1 if blocking else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
