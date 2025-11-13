from typing import Dict
import re

def to_html_ruby(content: str) -> str:
    """
    Convert Ruby annotations in the content to HTML <ruby> tags.

    Parameters
    ----------
    content: str
        The content string containing Ruby annotations in the format
        "|{base_text}<{annotation}>".

    Returns
    -------
    output: str
        The content string with Ruby annotations converted to HTML <ruby> tags.

    Examples
    --------
    >>> content = "|漢字<かんじ> is a Japanese word."
    >>> to_html_ruby(content)
    '<ruby>漢字<rt>かんじ</rt></ruby> is a Japanese word.'
    >>> content = "This is a test without ruby."
    >>> to_html_ruby(content)
    'This is a test without ruby.'
    >>> content = "|複雑<ふくざつ>な|例<れい>です。"
    >>> to_html_ruby(content)
    '<ruby>複雑<rt>ふくざつ</rt></ruby>な<ruby>例<rt>れい</rt></ruby>です。'
    """
    def replace_ruby(match: re.Match) -> str:
        base_text = match.group(1)
        annotation = match.group(2)
        return f'<ruby>{base_text}<rt>{annotation}</rt></ruby>'

    pattern = r'\|([^<|]+)<([^>]+)>'
    output = re.sub(pattern, replace_ruby, content)
    return output


class JsonKeyDuplicateError(Exception):
    """Raised when duplicate top-level (H1) keys are found in the Markdown file."""

def md_to_json(path: str) -> dict:
    """
    Convert a Markdown file to a JSON representation.
    Rules:
      - Only top-level headers (`# `) are keys.
      - The text between two top-level headers (including lower-level headers) is the value.
      - Content before the first top-level header is ignored.
      - Duplicate top-level headers raise JsonKeyDuplicateError.

    Parameters
    ----------
    path: str
        The file path to the Markdown file of which encoding is UTF-8.
        h1 header represents key and the content under h1 represents value.

    Returns
    -------
    output: dict
        A JSON representation of the Markdown content.

    Raises
    ------
    JsonKeyDuplicateError
        If duplicate keys are found in the Markdown file.
    """
    result: Dict[str, str] = {}
    current_key = None
    buffer: list[str] = []

    with open(path, "r", encoding="utf-8") as f:
        for raw_line in f:
            line = raw_line.rstrip("\n")

            # Detect H1 header (allow optional leading spaces)
            stripped = line.lstrip()
            if stripped.startswith("# "):
                key = stripped[2:].strip()

                # If we were collecting for a previous key, flush it
                if current_key is not None:
                    value = "\n".join(buffer)
                    result[current_key] = value
                    buffer = []

                # Check duplicate keys
                if key in result:
                    raise JsonKeyDuplicateError(f"Duplicate key found: {key}")

                current_key = key
            else:
                # Only collect content if a top-level key has been started
                if current_key is not None:
                    buffer.append(line)

    # Flush the last collected value if any
    if current_key is not None:
        value = "\n".join(buffer)
        result[current_key] = value

    return result

if __name__ == "__main__":
    import doctest
    doctest.testmod()
    print("All tests passed.")
