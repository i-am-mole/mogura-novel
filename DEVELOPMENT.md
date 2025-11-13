# 個人サイト運用ルール

## 目的
このドキュメントはもぐらノベルトの開発・公開を GitHub Pages 上で安定的に運用するためのブランチ戦略・運用ルールをまとめたもの。

---

## ディレクトリ構成

├─ README.md  
├─ tools/ # 静的サイトジェネレータ（SSG）や補助ツール  
├─ private/ # 編集元。小説や設定資料、CSS などをここに置く  
│ ├─ css/style.css # サイト全体のスタイル  
│ └─ index.md # サイトトップ  
│ └─ <小説用ディレクトリ>  
│  ├── index.md # 小説トップ  
│  ├── その他 .md ファイル  
├─ public/ # SSG によって生成される公開用 HTML  
├─ data/ # 更新履歴など、サイトメンテナンスに必要なデータ  
└─ （その他、README.md やスクリプト等）  

## ブランチ運用方針

### 基本構成

| ブランチ | 用途 |
|-----------|------|
| `main` | 公開用ブランチ。`public/` の内容がこのまま GitHub Pages で配信される |
| 作業ブランチ | 一時的な作業単位。作業完了後に `main` にマージして削除 |

`main` は保護対象（直接 push 禁止）とし、作業は必ず別ブランチで行う。

## ブランチ命名規則

| 種別 | 命名例 | 用途 |
|------|---------|------|
| サイトコンテンツ追加 | `content/<workslug>-add-ep05` | 作品・章・エピソード追加 |
| サイトコンテンツ修正 | `content/<workslug>-fix-typo` | 文章修正やメタ情報更新 |
| SSG・ツール | `tool/feat-export-html`, `tool/fix-path` | Python スクリプト修正 |
| ドキュメント追加 | `doc/<doc-name>-add` | ドキュメント追加 |
| ドキュメント修正 | `doc/<doc-name>-fix-typo` | ドキュメント修正 |
| レイアウト調整 | `layout/header-tweak` | HTML 構造変更など |
| 緊急修正 | `hotfix/deploy-20251113-css` | 公開後の即時修正 |

## ブランチ単位
- 一つの論点に対して一つの短命ブランチ
- 一つのブランチで複数のサイトコンテンツは修正しない
- SSG, CSS 修正等のサイト全体に影響する修正に関しては専用のブランチを設けてそこで作業する（現時点では必要なし）

## 作業の流れ

### 1. ブランチを作成

```bash
git switch -c content/mywork-add-ep05
```

### 2. コンテンツ編集
[private/](private/) 配下を編集。HTML は SSG にべた書き、CSS は [private/css/style.css](private/css/style.css) に追記。

### 3. サイト生成

- [venv.bat](venv.bat) で Python 仮想環境を作成後する
- SSG を実行

```bash
python tools/publish.py
```

- public/ と data/update_history.csv が再生成される。

### 4. コミット
private/ と SSG の生成物をコミットする

```bash
git add -A private/ public/ data/update_history.csv
git commit -m "publish: update source and generated site"
```

### 5. main へマージ

```bash
git switch main
git pull --rebase
git merge --ff-only content/mywork-add-ep05
git push origin main
```

## コミットメッセージ指針

| Prefix    | 用途          |
| --------- | ----------- |
| `feat`    | 新機能・コンテンツ追加 |
| `fix`     | 不具合修正       |
| `docs`    | ドキュメント追加・更新 |
| `chore`   | 雑務（依存更新など）  |
| `publish` | SSG による出力更新 |

## タグ指針
private/ 以外の準備が整った時点を **mogura-novel-born** とするが他は未定！

```bash
# 全ての変更を main にマージ後に main ブランチで
git tag -a <tag-name> -m "<tag-description>"
git push origin <tag-name>
```