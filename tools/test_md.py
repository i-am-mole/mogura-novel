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
