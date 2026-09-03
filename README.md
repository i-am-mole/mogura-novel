# mogura-novel

趣味で書いている小説を公開する個人サイト[もぐらノベル](https://www.mogura-novel.com)のリポジトリです。`private/` の原稿と静的ファイルを正本とし、リポジトリ付属の静的サイトジェネレータ（SSG）が GitHub Pages の公開元である `docs/` を生成します。

## はじめに

手動で原稿を更新して公開する基本手順は次のとおりです。

1. `main` から用途に応じた作業ブランチを作る。
2. [原稿・静的ファイルの書式](CONTENT_GUIDE.md)に従って `private/` を編集する。
3. `venv.bat` を実行し、仮想環境を有効化したコマンドプロンプトを開く。
4. 開いたコマンドプロンプトのリポジトリルートで `python tools/publish.py` を実行する。
5. `private/`、`docs/`、`data/update_history.csv` の意図した差分を確認してコミットする。

`docs/` と `data/update_history.csv` は生成物です。通常は直接編集しません。詳しいブランチ運用、テスト、公開手順は [DEVELOPMENT.md](DEVELOPMENT.md) を参照してください。

Windows では GUI エディタも利用できます。`start_editor.bat` を実行し、操作方法は [EDITOR.md](EDITOR.md) を参照してください。

## ドキュメント案内

| 文書 | 扱う情報 |
| --- | --- |
| [CONTENT_GUIDE.md](CONTENT_GUIDE.md) | 自己紹介、作品情報、各話、画像、CSS の保存場所と書式、ルビ、章区切り |
| [DEVELOPMENT.md](DEVELOPMENT.md) | リポジトリ構成、環境構築、ブランチ、生成・テスト・公開手順 |
| [EDITOR.md](EDITOR.md) | Windows GUI エディタの機能、操作、制限 |
| [SSG_SPEC.md](SSG_SPEC.md) | SSG の入力・出力、更新日、依存関係、ハッシュ、冪等性 |
| [REPOST_EXPORT.md](REPOST_EXPORT.md) | 他の小説投稿サイト向けテキスト出力ツールの仕様と使い方 |

## 正本と生成物

| 種類 | 場所 | 編集方針 |
| --- | --- | --- |
| 原稿・公開用静的ファイル | `private/` | 人または GUI エディタが編集する正本 |
| 公開サイト | `docs/` | SSG が全体を再生成する GitHub Pages 公開元 |
| 更新履歴 | `data/update_history.csv` | SSG が管理する追跡対象データ |
| SSG・補助ツール | `tools/` | 実装と自動テスト |

ライセンスは [LICENSE.md](LICENSE.md) を参照してください。
