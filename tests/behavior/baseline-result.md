# Baseline Result

## Raw response

最像是「圓潤手寫泡泡字／胖體展示字」的客製化處理，接近日系可愛的膨脹字形；重點不在特定字型，而是奶油色內描邊、白色粗外框、右下短擠出與淡紫陰影的層次。

GPT Image 2 提示詞：

> 透明背景，僅生成繁體中文美術字「甜橙氣泡」，不可出現水果、飲料杯、標籤、圖案、人物或任何其他文字。字體為圓潤、膨脹、可愛的糖果泡泡字，筆畫厚實飽滿、略帶手寫感。字面由上方亮粉紅漸變至下方蜜桃橙，保留柔和立體高光；字內沿著筆畫加入細緻奶油白色內描邊，外圍加上厚實純白描邊。整組文字向右下方做短距離奶油色立體擠出，再加柔焦淡薰衣草紫投影；局部有小型白色亮點與果凍般光澤。邊緣乾淨、字距緊湊、置中構圖、高解析度 PNG、透明 Alpha 背景。

## Failed or ambiguous criteria

1. The response gives a combined conclusion — 「最像是「圓潤手寫泡泡字／胖體展示字」的客製化處理」 — but does not explicitly separate observed evidence from a font-name/category guess or state confidence.
2. The prompt rewrites the source lettering as 「甜橙氣泡」 rather than using 「夏日氣泡」 exactly once.
3. The exclusions are incomplete: 「不可出現水果、飲料杯、標籤、圖案、人物或任何其他文字」 does not explicitly rule out scenery, watermarks, or checkerboards.
4. The response invents target copy despite the user saying it is undecided: 「僅生成繁體中文美術字「甜橙氣泡」」.

## Rules the skill must add

- State observable lettering evidence separately from any font-family guess, and label the guess with a confidence level.
- Put the supplied source text exactly once in the prompt; never substitute or invent copy. If final copy is undecided, ask for it.
- Explicitly exclude scenery, watermarks, and checkerboard backgrounds alongside the unwanted screenshot elements.
