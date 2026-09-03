# 開発・公開ガイド

## 目的

この文書は、もぐらノベルを GitHub Pages で安定して公開するためのリポジトリ構成、環境構築、ブランチ運用、生成・検証・公開手順をまとめます。原稿の書式は [CONTENT_GUIDE.md](CONTENT_GUIDE.md)、SSG の内部仕様は [SSG_SPEC.md](SSG_SPEC.md) を参照してください。

## リポジトリ構成

```text
mogura-novel/
├─ README.md                 # プロジェクト概要と文書の入口
├─ CONTENT_GUIDE.md          # 原稿・静的ファイルの保存場所と書式
├─ DEVELOPMENT.md            # 開発・公開手順（この文書）
├─ EDITOR.md                 # Windows GUI エディタ仕様
├─ SSG_SPEC.md               # SSG の実装仕様
├─ REPOST_EXPORT.md          # 転載用テキスト出力ツール仕様
├─ LICENSE.md                # ライセンス
├─ requirements.txt          # Python 依存パッケージ
├─ start_editor.bat          # GUI エディタ起動・初回環境構築
├─ venv.bat                  # Windows 用仮想環境準備
├─ private/                  # 人が編集する原稿・静的ファイルの正本
├─ docs/                     # SSG が生成する GitHub Pages 公開物
├─ data/
│  └─ update_history.csv     # SSG が管理する入力別更新履歴
└─ tools/
   ├─ publish.py             # SSG のコマンドライン入口
   ├─ novel.py               # 作品の読込・検証・章構成
   ├─ story.py               # 各話の読込・検証
   ├─ toppage.py             # 自己紹介と作品一覧の読込
   ├─ md.py                  # Markdown・独自ルビ変換
   ├─ repost_export.py       # 転載用テキスト出力
   ├─ novel_editor.py        # GUI エディタの入口
   ├─ editor/                # GUI エディタ本体
   ├─ run_tests.py           # リポジトリ内一時領域を使うテストランナー
   └─ test_*.py              # 自動テスト
```

実行時には次の Git 追跡対象外ディレクトリが作られます。

| 場所 | 管理主体 | 内容 |
| --- | --- | --- |
| `.venv/` | Python | 仮想環境と依存パッケージ |
| `.novel-editor/` | エディタ・SSG・テスト | プレビュー、一時生成物、バックアップ、ごみ箱、テスト一時ファイル |
| `.repost-export/` | 転載ツール | 他サイトへ貼り付けるプレーンテキスト |

`private/` 内の詳細と `docs/` への対応は [CONTENT_GUIDE.md](CONTENT_GUIDE.md) を参照してください。

## 環境構築

Windows ではリポジトリルートで `venv.bat` を実行します。`.venv` がなければ作成し、`requirements.txt` の依存パッケージを導入したうえで、仮想環境を有効化済みのコマンドプロンプトが開きます。以降、この文書の `python` コマンドは、そのコマンドプロンプトでリポジトリルートから実行することを前提とします。GUI エディタだけを使う場合は `start_editor.bat` が不足している環境を初回起動時に準備します。

`venv.bat` を使わず手動で準備する場合は、仮想環境を作成して有効化してから依存パッケージを導入します。

```bat
python -m venv .venv
call .venv\Scripts\activate.bat
python -m pip install -r requirements.txt
```

## ブランチ運用

`main` は `docs/` の内容を GitHub Pages で公開するブランチです。直接変更せず、作業ごとに `main` から短命なブランチを作り、検証後にマージします。

### 命名規則

| 種別 | 命名例 | 用途 |
| --- | --- | --- |
| サイトコンテンツ追加 | `content/<work-slug>-add-ep05` | 作品・章・各話の追加 |
| サイトコンテンツ修正 | `content/<work-slug>-fix-typo` | 本文や作品情報の修正 |
| SSG・補助ツール | `tool/feat-export-html`、`tool/fix-path` | Python ツールの変更 |
| ドキュメント | `doc/content-guide-refactor` | 文書の追加・修正 |
| レイアウト | `layout/header-tweak` | CSS や HTML 構造の変更 |
| 緊急修正 | `hotfix/deploy-20251113-css` | 公開後の緊急修正 |

ブランチ名は小文字を基本とし、空白の代わりにハイフンを使います。一つの論点につき一つのブランチとし、無関係な変更を混ぜません。

```powershell
git switch main
git pull --rebase
git switch -c content/mywork-add-ep05
```

## 変更から公開まで

### 1. 入力を編集する

[CONTENT_GUIDE.md](CONTENT_GUIDE.md) に従って `private/` を編集します。`docs/` と `data/update_history.csv` は直接編集しません。

### 2. サイトを生成する

```bat
python tools/publish.py
```

SSG はサイト全体を一時領域へ生成し、検証と生成がすべて成功した場合だけ `docs/` と `data/update_history.csv` を置き換えます。更新日と差分範囲の仕様は [SSG_SPEC.md](SSG_SPEC.md) を参照してください。

### 3. テストと差分を確認する

```bat
python tools/run_tests.py
git status --short
git diff --stat
git diff --minimal
git diff --check
```

確認事項は次のとおりです。

- 自動テストがすべて成功する。
- 入力検証エラーがなく、意図した HTML が生成される。
- 変更と無関係な作品へ、共通ヘッダーなど仕様上の依存範囲を超えた差分がない。
- 変更なしでもう一度 SSG を実行しても、新しい Git 差分が生じない。
- レイアウトや GUI を変更した場合は、ブラウザまたは GUI で手動確認する。

### 4. コミットする

原稿変更では、正本と生成物を同じコミットへ含めます。

```powershell
git add private docs data/update_history.csv
git commit -m "publish: update source and generated site"
```

ツールや文書だけを変更した場合は、変更したファイルだけを追加してください。

| 接頭辞 | 用途 |
| --- | --- |
| `feat` | 新機能・コンテンツ追加 |
| `fix` | 不具合修正 |
| `docs` | ドキュメント追加・更新 |
| `chore` | 依存更新などの保守作業 |
| `publish` | SSG による公開入力・出力更新 |

### 5. `main` へ反映する

```powershell
git switch main
git pull --rebase
git merge --ff-only content/mywork-add-ep05
git push origin main
```

GitHub Pages は `main` ブランチの `/docs` を公開元として設定している前提です。リポジトリ設定を変更した場合は、この前提と実際の Pages 設定が一致していることを確認してください。

## ファイル名変更・削除時の注意

公開済みの作品ディレクトリや話ファイルを手動で改名・削除すると、`data/update_history.csv` の古いキーが残ります。話ファイルの改名・削除は、履歴も更新する GUI エディタの機能を優先してください。作品ディレクトリの改名・削除は GUI エディタが対応していないため、実施時は更新履歴と公開 URL への影響を個別に確認します。

## タグ

初期リリースの目印として `mogura-novel-born` を使用します。新しいタグを作る場合は、すべての変更を `main` へ反映した後に実行します。

```powershell
git tag -a <tag-name> -m "<tag-description>"
git push origin <tag-name>
```
