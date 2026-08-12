---
name: svg-to-mermaid
description: Use when the user uploads or points to a vector flowchart (SVG) and wants it converted to text that expresses the flow logic, or asks to turn a diagram into Mermaid. Parses the SVG into structured nodes/edges, then produces a renderable Mermaid flowchart.
---

# SVG 流程图 → Mermaid 文本

将用户上传的 SVG 矢量流程图转换为能表达其逻辑的 Mermaid 文本。

## 处理步骤

1. 定位 SVG 文件:优先检查 `.reasonix/attachments/`,其次用户明确给出的路径。
2. 运行脚本提取结构:

   ```bash
   python3 .reasonix/skills/svg-to-mermaid/scripts/svg2struct.py <file.svg>
   ```

   输出为 JSON 中间表示:`{"nodes":[{"id","text","type","cx","cy"}], "edges":[{"from","to","label"}], "swimlanes":[{"id","label","cx","cy","w","h"}]}`。
3. 基于 JSON 组织 Mermaid:
   - `flowchart TD`(整体高度 > 宽度时)或 `flowchart LR`(宽度 > 高度时)
   - 节点符号:`type=rect → A[文字]`;`diamond → B{文字?}`;`ellipse → C((文字))`;`text → A[文字]`
   - 边:`from --> to`;`label` 非空时 `from -->|label| to`
   - 泳道:JSON 的 `swimlanes` 数组非空时,按各泳道 `cx` 左右排序,把落入对应泳道 `w/h` 范围(x 坐标在该泳道区间内)的节点归入该 `subgraph`,标签用泳道 `label`:

     ```mermaid
     flowchart TD
         subgraph 接收
             n0[接收请求]
         end
         subgraph 处理
             n1[校验]
         end
         subgraph 输出
             n2[返回结果]
         end
         n0 --> n1 --> n2
     ```
4. 输出 Mermaid 代码块,并附一句"可粘贴到 mermaid.live 或支持 Mermaid 的文档中渲染"。

## 边界情况

- **无箭头**:脚本输出 `directed` 信息;若全图无箭头,按从上到下、从左到右推断流向。
- **循环回路**:JSON 中回边(如 `n2 --> n1`)直接输出,不强行展开。
- **孤立文字/形状**:保留为独立节点;无法归属的 `<image>` 位图内容用 `%% 无法读取的位图` 注释标注。
- **脚本报错**:将错误信息与 SVG 片段一并呈现,说明结构不被支持,不臆造流程。

## 输出规范

- 必须是合法 Mermaid 语法(以 `flowchart` 开头,`-->` 连接)
- 保留所有节点文字与连线标签,不翻译、不改写
- 分支/判断用 `{}` 节点,标签用 `|是|`/`|否|` 表达
