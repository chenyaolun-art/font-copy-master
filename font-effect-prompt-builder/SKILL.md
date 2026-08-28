---
name: font-effect-prompt-builder
description: Use when a user provides a screenshot or reference image of stylized lettering and wants its font, lettering treatment, or ChatGPT/GPT Image 2 prompt reconstructed for original or replacement copy.
---

# 美術字提示詞分析器

輸入必須是可讀的參考圖；可見文字不清楚時，詢問原始文字。若已提供目標文案，直接採用，不重問。

## 工作流程

1. 依[視覺分析](references/visual-analysis.md)檢視圖片，依固定欄位報告：來源文字／語種／文字系統、字體候選／類別／信心／證據、字形改造、排版、效果層次與應排除元素。先說可觀察字形特徵；沒有證據不得宣稱確定。
2. 撰寫一段原始文字的完整中文 GPT Image 2 提示詞。提示詞以繁體中文為主，原文以引號包住且逐字只出現一次。
3. 只在缺少目標文案時詢問。取得後保留文案完全原樣，只調整為適合字數的排版，輸出一段最終完整提示詞；不生成圖片。
4. 明確詢問是否要歸檔。僅在使用者清楚最終確認後，且有可讀的本機參考圖絕對路徑時，讀取[分類法](references/taxonomy.md)與[案例結構](references/case-schema.md)，建立符合結構的暫存 metadata JSON。解析本技能 `scripts/archive_case.py` 的絕對路徑，並以 metadata 與 image 的絕對路徑執行。成功才回報 `case_id`、`case_dir`、索引路徑；失敗不可聲稱已儲存。草稿、隨口同意或沉默都不是確認。

## 不變條件

- 提示詞只描述字體與附著效果；即使列出字體候選，也必須寫出可觀察字形特徵。
- 排除額外文字、符號、圖示、人物、道具、場景、邊框、水印、標誌、棋盤格及無關裝飾。
- 要求完全透明的孤立背景；可設定時使用 `background="transparent"` 與 PNG／WebP alpha，否則用純色高對比背景作回退。原本附著的陰影可保留。
- 不把截圖中的場景物件自動視為字效；不在 v1 生成影像。

提示詞格式與範例見[Image 2 提示詞規格](references/image2-prompt-spec.md)。
