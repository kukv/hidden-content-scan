#!/usr/bin/env python3
"""人のレビューで見えない内容を検知する。

対象は「差分を目視しても気づけない」もの:
  - 不可視 / 書式制御の Unicode(Trojan Source、ゼロ幅、LLM だけが読むタグ文字)
  - 同形異字(ラテン文字に化けたキリル・ギリシャ文字)
  - AI 指示ファイルの、レンダリングすると消える記述
  - GitHub の差分表示を抑止する .gitattributes 設定

標準ライブラリのみで動く(依存を増やすと action 自体が供給網の弱点になるため)。
"""
from __future__ import annotations

import argparse
import fnmatch
import re
import sys
import unicodedata
from dataclasses import dataclass

# --- 不可視 / 書式制御 ------------------------------------------------------
BIDI = set(range(0x202A, 0x202F)) | set(range(0x2066, 0x206A))
ZERO_WIDTH = {0x200B, 0x200C, 0xFEFF, 0x00AD, 0x180E, 0x3164, 0x115F, 0x1160, 0xFFA0}
INVISIBLE_MATH = set(range(0x2060, 0x2065))
ANNOTATION = set(range(0xFFF9, 0xFFFC))
TAG_CHARS = set(range(0xE0000, 0xE0080))
PRIVATE_USE = set(range(0xE000, 0xF900)) | set(range(0xF0000, 0x10FFFE))
ODD_SPACE = {0x00A0, 0x202F, 0x205F, 0x3000} | set(range(0x2000, 0x200B))
EMOJI_JOINERS = {0xFE0F, 0x200D}

# --- AI 指示ファイル --------------------------------------------------------
AI_FILENAMES = {
    "CLAUDE.md", "CLAUDE.local.md", "AGENTS.md", "GEMINI.md",
    ".cursorrules", ".clinerules", ".windsurfrules", "copilot-instructions.md",
}
AI_DIR_MARKERS = ("/.claude/", "/.cursor/", "/.github/instructions/")

HIDDEN_MARKUP = [
    (re.compile(r"<!--"), "HTML コメント(レンダリング時に消える)"),
    (re.compile(r"<details\b", re.I), "details による折り畳み"),
    (re.compile(r"display\s*:\s*none", re.I), "display:none"),
    (re.compile(r"visibility\s*:\s*hidden", re.I), "visibility:hidden"),
    (re.compile(r"font-size\s*:\s*0", re.I), "font-size:0"),
    (re.compile(r"opacity\s*:\s*0(?![.\d])", re.I), "opacity:0"),
    (re.compile(r"color\s*:\s*(#f{3}\b|#f{6}\b|white|transparent)", re.I), "背景と同化する文字色"),
]

# 差分表示を抑止する指定。`binary` は画像・フォントなど本物のバイナリに付ける
# のが普通なので、テキストになり得る対象に付いているときだけ問題にする。
BINARY_EXTENSIONS = {
    "png", "jpg", "jpeg", "gif", "ico", "icns", "bmp", "webp", "avif", "svgz",
    "woff", "woff2", "ttf", "otf", "eot", "pdf", "zip", "gz", "tgz", "bz2", "xz",
    "7z", "rar", "jar", "war", "ear", "class", "so", "dylib", "dll", "exe", "bin",
    "wasm", "mp3", "mp4", "mov", "avi", "webm", "ogg", "wav", "keystore", "jks",
    "p12", "pfx", "der", "db", "sqlite", "parquet", "xlsx", "docx", "pptx",
}
DIFF_SUPPRESSORS = re.compile(r"(?<![\w-])(-diff|linguist-generated(=true)?|binary)(?![\w-])")

# 文字クラスはエスケープで書く。ここにキリル・ギリシャ文字を直接置くと、
# この検査自身が自分のソースを mixed-script として検知してしまう。
TOKEN = re.compile("[0-9A-Za-z_\u0370-\u03ff\u0400-\u04ff]+")

# 既定で警告どまりにするルール(実リポで正当な用例が多いもの。
# private-use は Nerd Font のアイコンに使われる)
DEFAULT_REPORT_ONLY = {"odd-space", "long-line", "base64-blob", "private-use"}

LONG_LINE = 2000
BASE64_BLOB = re.compile(r"[A-Za-z0-9+/]{500,}={0,2}")


@dataclass
class Finding:
    rule: str
    path: str
    line: int
    col: int
    detail: str


def _script_of(ch: str) -> str | None:
    cp = ord(ch)
    if 0x0400 <= cp <= 0x04FF:
        return "Cyrillic"
    if 0x0370 <= cp <= 0x03FF:
        return "Greek"
    if ch.isascii() and ch.isalpha():
        return "Latin"
    return None


def _emoji_ish(cp: int) -> bool:
    return (
        0x1F000 <= cp <= 0x1FAFF
        or 0x2600 <= cp <= 0x27BF
        or cp in (0x2B50, 0x2B55, 0xFE0F, 0x200D, 0x00A9, 0x00AE, 0x203C, 0x2049)
    )


def _is_ai_instruction_file(path: str) -> bool:
    name = path.rsplit("/", 1)[-1]
    if name in AI_FILENAMES or name.endswith(".mdc"):
        return True
    return any(marker in "/" + path for marker in AI_DIR_MARKERS)


def _name_of(ch: str) -> str:
    return unicodedata.name(ch, "UNNAMED")


def scan_text(path: str, text: str) -> list[Finding]:
    out: list[Finding] = []
    ai_file = _is_ai_instruction_file(path)
    gitattributes = path == ".gitattributes" or path.endswith("/.gitattributes")

    for lineno, line in enumerate(text.splitlines(), 1):
        for col, ch in enumerate(line, 1):
            cp = ord(ch)
            if cp in BIDI:
                out.append(Finding("bidi", path, lineno, col, f"U+{cp:04X} {_name_of(ch)}"))
            elif cp in ZERO_WIDTH or cp in INVISIBLE_MATH or cp in ANNOTATION:
                out.append(Finding("zero-width", path, lineno, col, f"U+{cp:04X} {_name_of(ch)}"))
            elif cp in TAG_CHARS:
                out.append(Finding("tag-chars", path, lineno, col, f"U+{cp:04X} {_name_of(ch)}"))
            elif cp in PRIVATE_USE:
                out.append(Finding("private-use", path, lineno, col, f"U+{cp:04X} 私用領域"))
            elif cp in ODD_SPACE:
                out.append(Finding("odd-space", path, lineno, col, f"U+{cp:04X} {_name_of(ch)}"))
            elif cp in EMOJI_JOINERS:
                prev = ord(line[col - 2]) if col >= 2 else 0
                if not _emoji_ish(prev):
                    out.append(Finding("stray-joiner", path, lineno, col, f"U+{cp:04X} 絵文字以外への付与"))

        for match in TOKEN.finditer(line):
            scripts = {s for s in (_script_of(c) for c in match.group()) if s}
            if len(scripts) > 1:
                out.append(Finding("mixed-script", path, lineno, match.start() + 1,
                                   f"{match.group()} に {'+'.join(sorted(scripts))} が混在"))

        if len(line) > LONG_LINE:
            out.append(Finding("long-line", path, lineno, 1, f"{len(line)} 文字(差分が既定で開かれない)"))
        if BASE64_BLOB.search(line):
            out.append(Finding("base64-blob", path, lineno, 1, "長大な base64 らしき塊"))

        if ai_file:
            for pattern, label in HIDDEN_MARKUP:
                m = pattern.search(line)
                if m:
                    out.append(Finding("hidden-markup", path, lineno, m.start() + 1, label))

    if gitattributes:
        out.extend(_scan_gitattributes(path, text))
    return out


def _scan_gitattributes(path: str, text: str) -> list[Finding]:
    out: list[Finding] = []
    for lineno, line in enumerate(text.splitlines(), 1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        match = DIFF_SUPPRESSORS.search(stripped)
        if not match:
            continue
        pattern = stripped.split()[0]
        ext = pattern.rsplit(".", 1)[-1].lower() if "." in pattern else ""
        if match.group(1) == "binary" and ext in BINARY_EXTENSIONS:
            continue  # 画像やフォントへの binary 指定は正当
        out.append(Finding("diff-hiding", path, lineno, 1,
                           f"{pattern} の差分が GitHub で開かれなくなる({match.group(1)})"))
    return out


def scan_file(path: str) -> list[Finding]:
    try:
        with open(path, encoding="utf-8") as f:
            text = f.read()
    except (UnicodeDecodeError, OSError):
        return []  # バイナリ・読めないものは対象外(呼び出し側が git grep -I で除外済み)
    return scan_text(path, text)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("files", nargs="*")
    parser.add_argument("--report-only", default=",".join(sorted(DEFAULT_REPORT_ONLY)),
                        help="失敗させず報告だけするルール(カンマ区切り)")
    parser.add_argument("--exclude", default="", help="除外する glob(カンマ区切り)")
    parser.add_argument("--github-annotations", action="store_true",
                        help="GitHub Actions のアノテーション形式でも出力する")
    args = parser.parse_args(argv)

    report_only = {r.strip() for r in args.report_only.split(",") if r.strip()}
    excludes = [g.strip() for g in args.exclude.split(",") if g.strip()]

    findings: list[Finding] = []
    for path in args.files:
        if any(fnmatch.fnmatch(path, g) for g in excludes):
            continue
        findings.extend(scan_file(path))

    blocking = [f for f in findings if f.rule not in report_only]
    warnings = [f for f in findings if f.rule in report_only]

    for label, group in (("ERROR", blocking), ("WARN", warnings)):
        for f in group:
            print(f"{label} {f.path}:{f.line}:{f.col}: [{f.rule}] {f.detail}")
            if args.github_annotations:
                kind = "error" if label == "ERROR" else "warning"
                print(f"::{kind} file={f.path},line={f.line},col={f.col}::[{f.rule}] {f.detail}")

    print(f"\nscanned {len(args.files)} files: {len(blocking)} error(s), {len(warnings)} warning(s)")
    return 1 if blocking else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
