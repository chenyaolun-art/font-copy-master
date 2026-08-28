# 案例歸檔結構

歸檔前必須有可讀的本機參考圖絕對路徑，且 `confirmed` 必須為 `true`。metadata JSON 的必填欄位為：`confirmed`、`source_text`、`target_text`、`language`、`script`、`font_analysis`、`visual_analysis`、`original_prompt`、`final_prompt`、`style_tags`、`effect_tags`、`classification_notes`。

`font_analysis` 必含 `candidates`（最多 3 個）、`category`、`confidence`（`low`、`medium` 或 `high`）、`evidence`、`custom_modifications`。`style_tags` 與 `effect_tags` 必須是非空清單；兩者以及語種與文字系統必須使用分類法的正規值；使用 `other` 時，`classification_notes` 不可為空。

```json
{
  "confirmed": true,
  "source_text": "夏日氣泡",
  "target_text": "週末放風計畫",
  "language": "traditional-chinese",
  "script": "han",
  "font_analysis": {
    "candidates": ["JF Open 粉圓"],
    "category": "圓體展示字",
    "confidence": "medium",
    "evidence": "筆畫飽滿、轉角圓潤、內白寬。",
    "custom_modifications": "末端加粗並加入氣泡高光。"
  },
  "visual_analysis": "置中單行；藍綠漸層、白色內線、深色描邊與右下附著陰影。",
  "original_prompt": "渲染精確文字「夏日氣泡」的孤立圓潤美術字。",
  "final_prompt": "渲染精確文字「週末放風計畫」的孤立圓潤美術字。",
  "style_tags": ["cute", "playful"],
  "effect_tags": ["gradient", "inline", "outline", "plastic", "shadow"],
  "classification_notes": ""
}
```

先將 metadata 寫入暫存 JSON，並解析此技能的 `scripts/archive_case.py` 絕對路徑；只以絕對路徑執行：

```text
python3 /絕對路徑/font-effect-prompt-builder/scripts/archive_case.py --metadata /絕對路徑/metadata.json --image /絕對路徑/reference.png
```

成功 JSON 會提供 `case_id`、`case_dir` 和 `index_path`（索引）。重複的參考圖會因 SHA-256 去重而失敗，不可宣稱儲存成功。歸檔會保留原始副檔名但轉為小寫。
