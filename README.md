# hidden-content-scan

人のレビューで**見えない**内容を検知する GitHub Action。

差分を目で追っても気づけない形で紛れ込む「隠れた実装コード」と「隠れたプロンプト」を止めることが目的。

## 使い方

```yaml
      - uses: kukv/hidden-content-scan@<commit sha> # vX.Y.Z
```

対象は既定で **git 管理下のテキストファイル全部**（バイナリは除外）。AI エージェントへの指示ファイル（`CLAUDE.md`、`AGENTS.md`、`.cursorrules`、`.claude/**` など）も含む。

### 入力

| 入力 | 既定 | 説明 |
|---|---|---|
| `files` | git 管理下のテキストファイル | 検査対象（改行区切り） |
| `exclude` | なし | 除外する glob（カンマ区切り）。例 `**/testdata/**` |
| `report-only` | `odd-space,long-line,base64-blob,private-use` | 検知しても失敗させないルール |
| `working-directory` | `.` | 実行ディレクトリ |

### 例: テストデータを除外する

```yaml
      - uses: kukv/hidden-content-scan@<commit sha> # vX.Y.Z
        with:
          exclude: "**/testdata/**"
```

## 検知するもの

| ルール | 内容 | 既定 |
|---|---|---|
| `bidi` | 双方向制御文字（Trojan Source）。表示順とコンパイル順をずらす | **失敗** |
| `zero-width` | ゼロ幅・不可視文字（U+200B/200C/FEFF/00AD/180E、ハングル填字、不可視演算子、注釈文字） | **失敗** |
| `tag-chars` | タグ文字 U+E0000–E007F。**人には見えず LLM だけが読む**プロンプトの埋め込みに使われる | **失敗** |
| `stray-joiner` | 絵文字以外に付いた U+FE0F / U+200D | **失敗** |
| `mixed-script` | 同形異字。1 トークン内でラテン文字とキリル/ギリシャ文字が混在（`admin` の `a` をキリル文字 U+0430 に差し替える、など） | **失敗** |
| `hidden-markup` | AI 指示ファイル内の、レンダリングすると消える記述（HTML コメント、`<details>`、`display:none`、背景と同化する文字色） | **失敗** |
| `diff-hiding` | `.gitattributes` の `-diff` / `linguist-generated` / テキストへの `binary` 指定。GitHub の PR 画面で中身が表示されなくなる | **失敗** |
| `private-use` | 私用領域の文字。Nerd Font のアイコンで正当に使われる | 警告 |
| `odd-space` | NBSP など通常と異なる空白 | 警告 |
| `long-line` | 2000 文字超の行。GitHub が差分を既定で開かない | 警告 |
| `base64-blob` | 500 文字以上の base64 らしき塊 | 警告 |

`report-only` 入力で、失敗させる／警告どまりにする の振り分けを変えられる。

## 検知しないもの

- **見えているが誤読させる**コード（紛らわしい命名、巧妙なロジック）— レビューそのものの責務
- 依存ライブラリの中身 — SCA（osv-scanner）の領域
- ビルド成果物に埋め込まれたコード — 生成元をレビュー対象にする運用で担保する

## 設計

- **標準ライブラリのみ**で動く（`scripts/scan.py`）。検査する側が依存を持つと、そこが供給網の弱点になるため
- 判定は許可リストではなくコードポイント集合。絵文字の異体字セレクタ（U+FE0F）や ZWJ は、**直前が絵文字のときだけ**許容する（絵文字入りドキュメントで誤検知しないため）
- 同形異字はトークン単位のスクリプト混在だけを見る。日本語＋ラテン文字の混在は正当なので対象外

## 開発

```bash
./tests/run.sh                      # 検体に対する期待どおりの検知を確認
python3 scripts/scan.py <files...>  # 手元で実行
```
