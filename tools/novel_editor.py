from pathlib import Path
import sys


def main() -> None:
    tools_dir = Path(__file__).resolve().parent
    if str(tools_dir) not in sys.path:
        sys.path.insert(0, str(tools_dir))
    from editor.app import NovelEditorApp

    NovelEditorApp(tools_dir.parent).run()


if __name__ == "__main__":
    main()
