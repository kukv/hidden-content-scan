# hidden-content-scan

[English](README.md)

人のレビューで**見えない**内容を検知する GitHub Action。

差分を目で追っても気づけない形で紛れ込む「隠れた実装コード」と「隠れたプロンプト」を止めることが目的。

## 使い方

```yaml
      - uses: kukv/hidden-content-scan@<commit sha> # vX.Y.Z
```

対象は既定で **git 管理下のテキストファイル全部**（バイナリは除外）。AI エージェントへの指示ファイル（`CLAUDE.md`、`AGENTS.md`、`.cursorrules`、`.claude/**` など）と、それらが `@path` で取り込むファイルも含む。ファイル名も検査する。

既定モードでは、ファイルの中身をチェックアウトした作業ツリーではなく git の index（GitHub 上でレビューする内容）から読む。そのため `.gitattributes` の設定（`-diff`、`working-tree-encoding`、filter）やランナーのファイルシステムによって、検査対象や検査する中身が変わることはない。

### 入力

| 入力 | 既定 | 説明 |
|---|---|---|
| `files` | git 管理下のテキストファイル | 検査対象（改行区切り、パスはそのまま書く）。読めないエントリがあるとジョブを失敗させる（`unreadable`） |
| `exclude` | なし | 除外する glob（カンマ区切り）。例 `**/testdata/**`。`*` と `?` は 1 階層の中だけ、`**` は階層をまたいで一致する |
| `report-only` | `odd-space,long-line,base64-blob,private-use,invalid-utf8` | 検知しても失敗させないルール |
| `working-directory` | `.` | 実行ディレクトリ。検査するのはその配下だけなので、上の階層にある `.gitattributes` や指示ファイルは対象外になる |

`files` を `git diff` から作る場合は、パスをそのまま出力させる: `git -c core.quotePath=false diff --name-only --diff-filter=d`。
素の `git diff --name-only` は非 ASCII のファイル名をクォートし（`"caf\303\251.py"`）、削除したファイルも並べる。どちらも `unreadable` で失敗する。

### 例: テストデータを除外する

```yaml
      - uses: kukv/hidden-content-scan@<commit sha> # vX.Y.Z
        with:
          exclude: "**/testdata/**"
```

### 例: 厳密モード

UTF-8 として不正なファイルも必ず検査する（不正なバイトは置換してデコードする）。不正なバイト自体は既定では警告だけになる。これも失敗させたい場合は `report-only` から `invalid-utf8` を外す。

```yaml
      - uses: kukv/hidden-content-scan@<commit sha> # vX.Y.Z
        with:
          report-only: "odd-space,long-line,base64-blob,private-use"
```

`report-only: ""` にすると、すべてのルールでジョブを失敗させる。

## 検知するもの

| ルール | 内容 | 既定 |
|---|---|---|
| `bidi` | 双方向制御文字（Trojan Source）。表示順とコンパイル順をずらす。暗黙の方向マーク LRM/RLM/ALM も含む | **失敗** |
| `zero-width` | ゼロ幅・不可視文字。書式文字（Unicode のカテゴリ Cf）すべて、ハングル填字、CGJ、モンゴル文字・クメール文字の不可視記号、U+2028/2029/NEL、そして CJK 漢字や記号に 1 つだけ付くもの以外の異体字セレクタ（「絵文字への密輸」に使われる） | **失敗** |
| `tag-chars` | タグ文字 U+E0000–E007F。**人には見えず LLM だけが読む**プロンプトの埋め込みに使われる | **失敗** |
| `stray-joiner` | 絵文字の直後にない U+FE0F と、2 つの絵文字をつないでいない U+200D | **失敗** |
| `mixed-script` | 同形異字。1 トークン内でラテン文字とキリル/ギリシャ文字（Cyrillic Supplement や Greek Extended などのブロックも含む）が混在（`admin` の `a` をキリル文字 U+0430 に差し替える、など）。不可視文字を挟んでトークンを分割しても検知する | **失敗** |
| `hidden-markup` | AI 指示ファイル内の、レンダリングすると消える記述（HTML コメント、`<details>`、`display:none`、`opacity:0`、背景と同化する文字色。HTML 実体参照や CSS エスケープで書いたものも含む。`[//]: # (...)` などのリンク参照定義、`<?...?>`、`<!...>`、CDATA）。フェンスで囲んだコードブロックはそのまま表示されるので対象外 | **失敗** |
| `diff-hiding` | `.gitattributes` の `-diff` / `linguist-generated` / テキストへの `binary` 指定と、それらに展開されるマクロ。見た目と違う解釈をさせる制御文字や特殊な空白も含む。GitHub の PR 画面で中身が表示されなくなる | **失敗** |
| `unreadable` | 検査対象として指定されたのに読めないファイル（存在しない、ディレクトリ、リポジトリに blob がない） | **失敗** |
| `invalid-utf8` | UTF-8 として不正なバイト。ファイル自体は検査する | 警告 |
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
- 判定は許可リストではなく Unicode の文字属性とコードポイント集合。絵文字の異体字セレクタ（U+FE0F）や ZWJ は**実際の絵文字シーケンスの中だけ**、異体字セレクタ 1 つは CJK 漢字か記号に付くときだけ許容する（絵文字や異体字を含むドキュメントで誤検知しないため）
- 同形異字はトークン単位のスクリプト混在だけを見る。日本語＋ラテン文字の混在は正当なので対象外

## セキュリティ上の注意

- この action はチェックアウトした内容を実行しない。ファイル名はコマンドラインに渡さず、Python は隔離モード（`python3 -I`）で動かすので、リポジトリ内のファイルがモジュールを差し替えることもない。
- これが言えるのはこのステップだけ。`pull_request_target` や `workflow_run` のようにシークレットを使えるワークフローで、PR のコードをビルド・実行するステップと組み合わせない。

## 開発

```bash
./tests/run.sh                      # 検体に対する期待どおりの検知を確認
python3 scripts/scan.py --git-index # action と同じく index を検査
python3 scripts/scan.py <files...>  # 指定したファイルを検査
```

ルールの追加方法と CI の検査内容は [CONTRIBUTING.md](CONTRIBUTING.md) を参照。

## ライセンス

[MIT](LICENSE)
