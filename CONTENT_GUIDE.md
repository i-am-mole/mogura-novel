# 原稿・静的ファイルの書式

## 目的

この文書は、もぐらノベルで公開する自己紹介、作品情報、各話、画像、CSS の保存場所と入力書式を定めます。公開手順は [DEVELOPMENT.md](DEVELOPMENT.md)、生成処理の内部仕様は [SSG_SPEC.md](SSG_SPEC.md) を参照してください。

## `private/` の構成

```text
private/
├─ self_intro.md                 # サイトトップの自己紹介
├─ CNAME                         # GitHub Pages のカスタムドメイン
├─ css/
│  └─ style.css                  # サイト全体のスタイル
├─ ogp/                          # 任意。OGP画像
│  ├─ default.png                # 任意。サイト共通画像
│  └─ <work-slug>.png            # 任意。作品別画像
├─ favicon.ico
├─ favicon-16x16.png
├─ favicon-32x32.png
├─ apple-touch-icon.png
└─ <work-slug>/                  # 作品ごとのディレクトリ
   ├─ index.md                   # 作品情報
   ├─ <episode-slug>.md          # 一話につき一ファイル
   ├─ -<episode-slug>.md         # 任意。非公開の書きかけ話
   └─ _<name>.md                 # 任意。SSGが話として読み込まないメモ
```

Markdown は BOM なし UTF-8 で保存します。作品情報と各話では、H1 見出し（`# `）がフィールド名として予約されています。フィールドより前に書いた内容は読み捨てられるため、記載しないでください。

SSG は `private/` 直下のうち `index.md` を持ち、ディレクトリ名が `-` で始まらないものを作品として検出します。GUI エディタと Windows の双方で扱えるよう、`work-slug` と `episode-slug` は小文字の半角英数字を単一のハイフンで区切ってください（例: `long-long-path`）。作品 slug に `blog`、`wiki`、`css`、Windows 予約名を使わず、話 slug に `index` を使わないでください。

未公開作品は、通常の作品と同じく `index.md` を作成し、ディレクトリ名を `-<work-slug>` とします。先頭の `-` が付いた作品は、配下の話を含めてSSGの検証、HTML生成、更新履歴の更新対象になりません。`index.md` を省略するとGUIエディタの作品一覧に現れないため、書きかけ作品の運用には使いません。

## 自己紹介

`private/self_intro.md` に通常の Markdown で記載します。SSG が必須として検証する条件は、空または空白だけではないことです。

サイト側が「自己紹介」の H2 見出しを付けるため、本文内で見出しを使う場合は H3 以下を推奨します。

## 作品情報

`private/<work-slug>/index.md` に次の形式で記載します。

```markdown
# title
作品タイトル
# tags
- タグ1
- タグ2
# status
連載中
# outline
作品のあらすじを Markdown で記載する。
# external links
- [公開先1](https://example.com/work1)
- [公開先2](https://example.com/work2)
# chapters
第一章: 10
第二章: 20
```

| フィールド | 必須 | 書式 |
| --- | --- | --- |
| `title` | 必須 | 空でない1行の作品タイトル |
| `tags` | 必須 | `- ` で始まる1件以上の Markdown リスト |
| `status` | 必須 | `連載中`、`完結済`、`更新停止` のいずれか |
| `outline` | 必須 | 空でない Markdown のあらすじ |
| `external links` | 任意 | `- [表示名](URL)` 形式の1件以上のリスト。リンクがなければ見出しごと省略する |
| `chapters` | 任意 | `章タイトル: 章区切り番号` を1行に1件。章分けしなければ見出しごと省略する |

上記以外の H1、必須フィールドの欠落、同じ H1 の重複、空のフィールドはエラーです。`chapters` の章タイトルと章区切り番号は、それぞれ作品内で重複できません。章区切り番号は整数で指定します。

## 各話

一話につき `private/<work-slug>/<episode-slug>.md` を一つ作り、次の形式で記載します。

```markdown
# title
話タイトル
# number
10
# content
本文を Markdown で記載する。
```

| フィールド | 必須 | 書式 |
| --- | --- | --- |
| `title` | 必須 | 空でない1行の話タイトル |
| `number` | 必須 | 整数の話数番号。表示順はこの数値の昇順 |
| `content` | 必須 | 空でない Markdown の本文 |

上記以外の H1、必須フィールドの欠落、同じ H1 の重複、空のフィールドはエラーです。`number` は同じ作品内で重複できません。

SSG が話として読み込むのは、作品ディレクトリ直下にある拡張子 `.md` のファイルのうち、`index.md` ではなく、ファイル名が `-` または `_` で始まらないものです。サブディレクトリ内の Markdown は読み込みません。

公開済み作品の書きかけ話は、episode-slug の先頭に `-` を付けます（例: `-episode-05.md`）。先頭の `-` が付いた話はSSGの検証、HTML生成、目次、文字数、更新日時の対象になりません。GUIエディタでは「非公開話」に表示され、通常どおり編集できます。公開できる状態になったら、エディタの「名前変更」で先頭の `-` を外します。`_` 始まりはエディタにも表示しないメモ用です。

## 章区切りと話数番号

`chapters` は各章に属する話数番号の上限を定めます。SSG は章区切り番号を昇順に並べ、各話を「話数番号以上である最小の章区切り番号」の章へ割り当てます。

```markdown
# chapters
第一章: 10
第二章: 20
```

この例では、話数番号 10 以下は第一章、11 以上 20 以下は第二章です。負の話数番号も整数として利用できます。最大の章区切り番号を超える話が一つでもあると検証エラーになります。空の章を定義することはできます。

## Markdown と独自ルビ

ルビは `|親文字<ルビ>` と記載します。

```text
|漢字<かんじ>
```

SSG がルビへ変換する場所は、自己紹介、作品タイトル、あらすじ、章タイトル、話タイトル、本文です。タグ、連載ステータス、外部リンクでは変換しません。

Markdown の通常改行は HTML の改行として維持されます。段落、リスト、リンクなど一般的な Markdown も使用できます。

## CSS、ドメイン、画像

- `private/css/style.css` は必須で、`docs/css/style.css` へ出力されます。
- `private/CNAME` は存在する場合に `docs/CNAME` へコピーされます。
- favicon は `private/` 直下の `favicon.ico`、`favicon-16x16.png`、`favicon-32x32.png`、`apple-touch-icon.png` を使用します。
- OGP 画像は任意です。`private/ogp/<work-slug>.png`、`private/ogp/default.png`、`private/apple-touch-icon.png`、`private/favicon-32x32.png` の順で候補が選ばれます。

`docs/` 側のファイルは SSG が再生成するため、直接編集しないでください。
