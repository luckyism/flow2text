#!/usr/bin/env python3
"""SVG 流程图 → 结构化中间表示(节点表 + 边表)。

仅使用标准库。输出 JSON 到 stdout(供 LLM 组织成 Mermaid)。
"""
import json
import re
import sys
import xml.etree.ElementTree as ET

NS = {"svg": "http://www.w3.org/2000/svg"}


def _tag(t):
    return t.split("}")[-1]  # 去掉命名空间前缀


def _parse_transform(transform):
    """解析 transform 字符串,返回 (tx, ty, sx, sy)。支持 translate/scale,忽略其余。"""
    tx = ty = 0.0
    sx = sy = 1.0
    if not transform:
        return tx, ty, sx, sy
    for m in re.finditer(r"(translate|scale)\(\s*([^)]+)\)", transform):
        kind, args = m.group(1), m.group(2).replace(",", " ").split()
        nums = [float(a) for a in args if a]
        if kind == "translate" and nums:
            tx, ty = nums[0], nums[1] if len(nums) > 1 else 0.0
        elif kind == "scale" and nums:
            sx = nums[0]
            sy = nums[1] if len(nums) > 1 else nums[0]
    return tx, ty, sx, sy


def _translate_point(x, y, transform):
    tx, ty, sx, sy = _parse_transform(transform)
    return x * sx + tx, y * sy + ty


def _parent_map(root):
    """构建 {子元素: 父元素} 映射,用于沿祖先链累积 transform。"""
    return {child: parent for parent in root.iter() for child in parent}


def _transforms(el, parent_map):
    """返回从根到该元素的 transform 字符串列表(祖先在前,自身在后)。"""
    chain = []
    cur = el
    while cur is not None:
        t = cur.get("transform")
        if t:
            chain.append(t)
        cur = parent_map.get(cur)
    return list(reversed(chain))


def _apply_transforms(x, y, transforms):
    """按顺序应用祖先→自身的 transform 链。"""
    for t in transforms:
        x, y = _translate_point(x, y, t)
    return x, y


def extract_texts(root):
    """提取所有 <text> 与 <foreignObject> 内嵌文字。"""
    parent_map = _parent_map(root)
    texts = []
    for i, el in enumerate(root.iter()):
        tag = _tag(el.tag)
        if tag == "text":
            parts = []
            for child in el.iter():
                if child.tag.split("}")[-1] == "tspan" and child.text:
                    parts.append(child.text)
                elif child.tag.split("}")[-1] == "text" and child.text:
                    parts.append(child.text)
            if not parts and el.text:
                parts.append(el.text)
            text = "".join(parts).strip()
            if not text:
                continue
            x = float(el.get("x", "0") or 0)
            y = float(el.get("y", "0") or 0)
            x, y = _apply_transforms(x, y, _transforms(el, parent_map))
            texts.append({"id": f"t{i}", "text": text, "type": "text",
                          "x": x, "y": y})
        elif tag == "foreignObject":
            div_text = "".join(el.itertext()).strip()
            if div_text:
                x = float(el.get("x", "0") or 0)
                y = float(el.get("y", "0") or 0)
                x, y = _apply_transforms(x, y, _transforms(el, parent_map))
                texts.append({"id": f"t{i}", "text": div_text, "type": "text",
                              "x": x, "y": y})
    return texts


def _shape_center(x, y, w, h):
    return x + w / 2.0, y + h / 2.0


def extract_shapes(root):
    parent_map = _parent_map(root)
    shapes = []
    for i, el in enumerate(root.iter()):
        tag = _tag(el.tag)
        transforms = _transforms(el, parent_map)
        if tag == "rect":
            x = float(el.get("x", "0") or 0)
            y = float(el.get("y", "0") or 0)
            w = float(el.get("width", "0") or 0)
            h = float(el.get("height", "0") or 0)
            cx, cy = _shape_center(x, y, w, h)
            cx, cy = _apply_transforms(cx, cy, transforms)
            # 大矩形(泳道/分区容器,如 draw.io swimlane)不作为流程节点
            kind = "container" if w > 150 and h > 150 else "rect"
            shapes.append({"id": f"s{i}", "type": kind,
                           "cx": cx, "cy": cy, "w": w, "h": h})
        elif tag == "ellipse":
            cx = float(el.get("cx", "0") or 0)
            cy = float(el.get("cy", "0") or 0)
            rx = float(el.get("rx", "0") or 0)
            ry = float(el.get("ry", "0") or 0)
            cx, cy = _apply_transforms(cx, cy, transforms)
            shapes.append({"id": f"s{i}", "type": "ellipse",
                           "cx": cx, "cy": cy, "w": rx * 2, "h": ry * 2})
        elif tag == "circle":
            cx = float(el.get("cx", "0") or 0)
            cy = float(el.get("cy", "0") or 0)
            r = float(el.get("r", "0") or 0)
            cx, cy = _apply_transforms(cx, cy, transforms)
            shapes.append({"id": f"s{i}", "type": "ellipse",
                           "cx": cx, "cy": cy, "w": r * 2, "h": r * 2})
        elif tag == "polygon":
            pts = el.get("points", "")
            coords = [float(v) for v in pts.replace(",", " ").split() if v]
            if len(coords) >= 6:
                xs = coords[0::2]
                ys = coords[1::2]
                cx = sum(xs) / len(xs)
                cy = sum(ys) / len(ys)
                cx, cy = _apply_transforms(cx, cy, transforms)
                kind = "diamond" if len(xs) == 4 else "polygon"
                shapes.append({"id": f"s{i}", "type": kind,
                               "cx": cx, "cy": cy,
                               "w": max(xs) - min(xs), "h": max(ys) - min(ys)})
    return shapes


def parse_svg(xml_text):
    root = ET.fromstring(xml_text)
    return {"nodes": extract_texts(root) + extract_shapes(root), "edges": []}


def main():
    if len(sys.argv) != 2:
        print("usage: svg2struct.py <file.svg>", file=sys.stderr)
        sys.exit(2)
    with open(sys.argv[1], encoding="utf-8") as f:
        print(json.dumps(parse_svg(f.read()), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
