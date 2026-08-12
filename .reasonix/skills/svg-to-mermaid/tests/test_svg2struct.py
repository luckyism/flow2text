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


class TestExtractShapes(unittest.TestCase):
    def test_shape_types_and_centers(self):
        root = svg2struct.parse_svg(load("shapes_sample.svg"))
        shapes = {s["id"]: s for s in root["nodes"]
                  if s["type"] != "text"}
        types = sorted(s["type"] for s in shapes.values())
        self.assertEqual(types, ["diamond", "ellipse", "rect", "rect"])
        rect1 = next(s for s in shapes.values() if s["cx"] == 80 and s["cy"] == 50)
        self.assertEqual(rect1["type"], "rect")
        self.assertEqual(rect1["w"], 120)
        self.assertEqual(rect1["h"], 40)
        # transform translate(0,100) 生效:第二个 rect 中心 y = 30+100+20 = 150
        rect2 = next(s for s in shapes.values() if s["cx"] == 70)
        self.assertEqual(rect2["cy"], 150)
        # polygon 4 点 → diamond
        dia = next(s for s in shapes.values() if s["type"] == "diamond")
        self.assertEqual(dia["cx"], 440)
        self.assertEqual(dia["cy"], 70)


class TestExtractEdges(unittest.TestCase):
    def test_edges_and_direction(self):
        edges = svg2struct.extract_edges(
            svg2struct._parse(load("edges_sample.svg")))
        self.assertEqual(len(edges), 3)
        directed = [e for e in edges if e["directed"]]
        undirected = [e for e in edges if not e["directed"]]
        self.assertEqual(len(directed), 2)
        self.assertEqual(len(undirected), 1)
        # polyline 终点 = 最后一个点
        poly = next(e for e in edges if e["x1"] == 30 and e["y1"] == 80)
        self.assertEqual((poly["x2"], poly["y2"]), (80, 150))


if __name__ == "__main__":
    unittest.main()
