import os
from tempfile import TemporaryDirectory
import unittest

import md


class TestToHtmlRuby(unittest.TestCase):
    def test_to_html_ruby(self):
        # Test case with ruby annotation
        content = "|漢字<かんじ> is a Japanese word."
        expected = '<ruby>漢字<rt>かんじ</rt></ruby> is a Japanese word.'
        self.assertEqual(md.to_html_ruby(content), expected)

        # Test case without ruby annotation
        content = "This is a test without ruby."
        expected = "This is a test without ruby."
        self.assertEqual(md.to_html_ruby(content), expected)

        # Test case with multiple ruby annotations
        content = "|複雑<ふくざつ>な|例<れい>です。"
        expected = '<ruby>複雑<rt>ふくざつ</rt></ruby>な<ruby>例<rt>れい</rt></ruby>です。'
        self.assertEqual(md.to_html_ruby(content), expected)

        # Test case with multiple lines
        content = """Here is |漢字<かんじ>.
And another |例<れい>.

And one more |例<れい> here.

Finally, no ruby here."""
        expected = """Here is <ruby>漢字<rt>かんじ</rt></ruby>.
And another <ruby>例<rt>れい</rt></ruby>.

And one more <ruby>例<rt>れい</rt></ruby> here.

Finally, no ruby here."""
        self.assertEqual(md.to_html_ruby(content), expected)


class TestToHtml(unittest.TestCase):
    def test_single_line_break_becomes_html5_br(self):
        content = "一行目です。\n二行目です。"
        expected = "<p>一行目です。<br>\n二行目です。</p>"
        self.assertEqual(md.to_html(content), expected)

    def test_blank_line_remains_a_paragraph_separator(self):
        content = "一段落目です。\n\n二段落目です。"
        expected = "<p>一段落目です。</p>\n<p>二段落目です。</p>"
        self.assertEqual(md.to_html(content), expected)

    def test_full_width_spaces_are_preserved(self):
        content = "　一行目です。\n　二行目です。\n\n　新しい段落です。\n文中の　空白です。"
        expected = (
            "<p>　一行目です。<br>\n　二行目です。</p>\n"
            "<p>　新しい段落です。<br>\n文中の　空白です。</p>"
        )
        self.assertEqual(md.to_html(content), expected)

    def test_half_width_spaces_are_not_replaced(self):
        content = "half width space"
        self.assertEqual(md.to_html(content), "<p>half width space</p>")

    def test_ruby_line_break_and_full_width_space_work_together(self):
        content = "　|漢字<かんじ>です。\n　次の|行<ぎょう>です。"
        expected = (
            "<p>　<ruby>漢字<rt>かんじ</rt></ruby>です。<br>\n"
            "　次の<ruby>行<rt>ぎょう</rt></ruby>です。</p>"
        )
        self.assertEqual(md.to_html(content), expected)

    def test_other_markdown_syntax_is_preserved(self):
        content = "## 見出し\n\n    x = 1\n    y = 2\n\n- **強調**\n- [リンク](https://example.com)"
        expected = (
            "<h2>見出し</h2>\n"
            "<pre><code>x = 1\ny = 2\n</code></pre>\n"
            "<ul>\n<li><strong>強調</strong></li>\n"
            '<li><a href="https://example.com">リンク</a></li>\n'
            "</ul>"
        )
        self.assertEqual(md.to_html(content), expected)

    def test_placeholder_like_content_does_not_collide(self):
        content = "MOGURAFULLWIDTHSPACE0PLACEHOLDER　本文"
        expected = "<p>MOGURAFULLWIDTHSPACE0PLACEHOLDER　本文</p>"
        self.assertEqual(md.to_html(content), expected)

    def test_conversion_is_stable(self):
        content = "　|漢字<かんじ>です。\n次の行です。"
        self.assertEqual(md.to_html(content), md.to_html(content))

def _write_file(dirpath: str, content: str, filename: str = "tmp.md") -> str:
    path = os.path.join(dirpath, filename)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    return path


class TestMdToJson(unittest.TestCase):
    def test_md_to_json_empty(self):
        md_content = "Hello world"
        with TemporaryDirectory() as d:
            path = _write_file(d, md_content)
            output = md.md_to_json(path)
            self.assertEqual(output, {})

    def test_md_to_json_duplicate_keys(self):
        md_content = """# key1
value1
# key1
value2
"""
        with TemporaryDirectory() as d:
            path = _write_file(d, md_content)
            with self.assertRaises(md.JsonKeyDuplicateError):
                md.md_to_json(path)

    def test_md_to_json_basic(self):
        md_content = """# key1
value1
# key2
1
# key3
-1001
# key4
# key5
The value of `key4` is empty because there is no text between the headers.
# key6
When there is any header of which level is lower than 1, it will be treated as part of the value.
## key6-1
This is a sub-header.
"""
        expected_output = {
            "key1": "value1",
            "key2": "1",
            "key3": "-1001",
            "key4": "", 
            "key5": "The value of `key4` is empty because there is no text between the headers.",
            "key6": "When there is any header of which level is lower than 1, it will be treated as part of the value.\n## key6-1\nThis is a sub-header.",
        }
        with TemporaryDirectory() as d:
            path = _write_file(d, md_content)
            output = md.md_to_json(path)
            self.assertEqual(output, expected_output)

    def test_md_to_json_no_h1(self):
        md_content = """## title
        This is a markdown file without h1 headers."""
        expected_output = {}
        with TemporaryDirectory() as d:
            path = _write_file(d, md_content)
            output = md.md_to_json(path)
            self.assertEqual(output, expected_output)

    def test_md_to_json_multiline_values(self):
        md_content = """# key1
This is a value
that spans multiple lines.
# key2
It also includes blank lines.

Value continues here.
"""
        expected_output = {
            "key1": "This is a value\nthat spans multiple lines.",
            "key2": "It also includes blank lines.\n\nValue continues here.",
        }
        with TemporaryDirectory() as d:
            path = _write_file(d, md_content)
            output = md.md_to_json(path)
            self.assertEqual(output, expected_output)

    def test_md_to_json_something_before_first_h1(self):
        md_content = """This text is before any h1 header.
# key1
value1
"""
        expected_output = {
            "key1": "value1",
        }
        with TemporaryDirectory() as d:
            path = _write_file(d, md_content)
            output = md.md_to_json(path)
            self.assertEqual(output, expected_output)

if __name__ == "__main__":
    unittest.main()
