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


def _in_defs(el, parent_map):
    """判断元素是否位于 <defs> 内(模板元素,不可见,须跳过)。"""
    cur = parent_map.get(el)
    while cur is not None:
        if _tag(cur.tag) == "defs":
            return True
        cur = parent_map.get(cur)
    return False


def extract_texts(root):
    """提取所有 <text> 与 <foreignObject> 内嵌文字。"""
    parent_map = _parent_map(root)
    texts = []
    for i, el in enumerate(root.iter()):
        tag = _tag(el.tag)
        if tag == "text":
            if _in_defs(el, parent_map):
                continue
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
            if _in_defs(el, parent_map):
                continue
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
            if _in_defs(el, parent_map):
                continue
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


def _parse(xml_text):
    return ET.fromstring(xml_text)


def _path_points(d):
    """解析 path 的 M/L/Q/C 命令,返回坐标点列表(best-effort)。"""
    pts = []
    for cmd, nums in re.findall(r"([MmLlCcQq])\s*([-\d.,\s]+)", d):
        vals = [float(v) for v in nums.replace(",", " ").split() if v]
        for i in range(0, len(vals) - 1, 2):
            pts.append((vals[i], vals[i + 1]))
    return pts


def extract_edges(root):
    parent_map = _parent_map(root)
    edges = []
    for i, el in enumerate(root.iter()):
        tag = _tag(el.tag)
        if tag not in ("line", "polyline", "path"):
            continue
        if _in_defs(el, parent_map):
            continue
        transforms = _transforms(el, parent_map)
        directed = False
        if el.get("marker-end"):
            directed = True
        # draw.io 用 endArrow 属性(可能挂在 style 里,已由转换后的属性承载)
        if el.get("endArrow") and el.get("endArrow") != "none":
            directed = True
        if tag == "line":
            x1 = float(el.get("x1", "0") or 0)
            y1 = float(el.get("y1", "0") or 0)
            x2 = float(el.get("x2", "0") or 0)
            y2 = float(el.get("y2", "0") or 0)
            x1, y1 = _apply_transforms(x1, y1, transforms)
            x2, y2 = _apply_transforms(x2, y2, transforms)
            edges.append({"id": f"e{i}", "x1": x1, "y1": y1,
                          "x2": x2, "y2": y2, "directed": directed})
        elif tag == "polyline":
            coords = [float(v) for v in
                      (el.get("points") or "").replace(",", " ").split() if v]
            if len(coords) >= 4:
                x1, y1 = _apply_transforms(coords[0], coords[1], transforms)
                x2, y2 = _apply_transforms(coords[-2], coords[-1], transforms)
                edges.append({"id": f"e{i}", "x1": x1, "y1": y1,
                              "x2": x2, "y2": y2, "directed": directed})
        elif tag == "path":
            pts = _path_points(el.get("d") or "")
            if len(pts) >= 2:
                x1, y1 = _apply_transforms(pts[0][0], pts[0][1], transforms)
                x2, y2 = _apply_transforms(pts[-1][0], pts[-1][1], transforms)
                edges.append({"id": f"e{i}", "x1": x1, "y1": y1,
                              "x2": x2, "y2": y2, "directed": directed})
    return edges


def _in_box(x, y, cx, cy, w, h, tol=8.0):
    half_w, half_h = w / 2.0 + tol, h / 2.0 + tol
    return abs(x - cx) <= half_w and abs(y - cy) <= half_h


def assemble_nodes(texts, shapes):
    nodes = []
    for shape in shapes:
        node = {"id": f"n{len(nodes)}", "text": "", "type": shape["type"],
                "cx": shape["cx"], "cy": shape["cy"],
                "w": shape["w"], "h": shape["h"]}
        nodes.append(node)
    for t in texts:
        owner = None
        for node in nodes:
            if "w" not in node:
                continue  # 独立 text 节点无包围盒,不做归属
            if _in_box(t["x"], t["y"], node["cx"], node["cy"],
                       node["w"], node["h"]):
                owner = node
                break
        if owner is not None:
            if not owner["text"]:
                owner["text"] = t["text"]
            else:
                owner["text"] += " " + t["text"]
        else:
            nodes.append({"id": f"n{len(nodes)}", "text": t["text"],
                          "type": "text", "x": t["x"], "y": t["y"],
                          "cx": t["x"], "cy": t["y"]})
    # 移除仅用于包围盒判断的 w/h
    for node in nodes:
        node.pop("w", None)
        node.pop("h", None)
    return nodes


def _nearest_node(x, y, nodes):
    best, best_d = None, float("inf")
    for node in nodes:
        d = (node["cx"] - x) ** 2 + (node["cy"] - y) ** 2
        if d < best_d:
            best, best_d = node, d
    return best


def _swimlanes(containers, texts):
    """从容器矩形提取泳道信息,label 取落入容器内的首个文字。"""
    lanes = []
    for c in containers:
        label = ""
        for t in texts:
            if _in_box(t["x"], t["y"], c["cx"], c["cy"], c["w"], c["h"]):
                if not label:
                    label = t["text"]
        lanes.append({"id": c["id"], "label": label,
                      "cx": c["cx"], "cy": c["cy"],
                      "w": c["w"], "h": c["h"]})
    return lanes


def match_edges(nodes, edges):
    result = []
    for e in edges:
        src = _nearest_node(e["x1"], e["y1"], nodes)
        dst = _nearest_node(e["x2"], e["y2"], nodes)
        if src is None or dst is None or src["id"] == dst["id"]:
            continue
        result.append({"from": src["id"], "to": dst["id"], "label": ""})
    return result


def parse_svg(xml_text):
    root = _parse(xml_text)
    texts = extract_texts(root)
    shapes = extract_shapes(root)
    containers = [s for s in shapes if s["type"] == "container"]
    flow_shapes = [s for s in shapes if s["type"] != "container"]
    swimlanes = _swimlanes(containers, texts)
    nodes = assemble_nodes(texts, flow_shapes)
    edges = match_edges(nodes, extract_edges(root))
    return {"nodes": nodes, "edges": edges, "swimlanes": swimlanes}


def main():
    if len(sys.argv) != 2:
        print("usage: svg2struct.py <file.svg>", file=sys.stderr)
        sys.exit(2)
    with open(sys.argv[1], encoding="utf-8") as f:
        print(json.dumps(parse_svg(f.read()), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
