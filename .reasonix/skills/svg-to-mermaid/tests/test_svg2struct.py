import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import svg2struct

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")


def load(name):
    with open(os.path.join(FIXTURES, name), encoding="utf-8") as f:
        return f.read()


class TestExtractTexts(unittest.TestCase):
    def test_plain_text_and_tspan(self):
        root = svg2struct.parse_svg(load("text_sample.svg"))
        texts = {t["text"]: t for t in root["nodes"] if t["type"] == "text"}
        self.assertIn("开始", texts)
        self.assertEqual(texts["开始"]["x"], 50)
        self.assertEqual(texts["开始"]["y"], 60)

    def test_transform_translate_applied(self):
        root = svg2struct.parse_svg(load("text_sample.svg"))
        texts = {t["text"]: t for t in root["nodes"] if t["type"] == "text"}
        self.assertIn("处理步骤", texts)  # tspan 合并
        self.assertEqual(texts["处理步骤"]["x"], 110)  # 10 + 100
        self.assertEqual(texts["处理步骤"]["y"], 50)  # 30 + 20


if __name__ == "__main__":
    unittest.main()
