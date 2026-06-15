# -*- coding: utf-8 -*-
import json
import os

# =================設定=================
INPUT_ORIGINAL = "data/classical_scores_suffix_filtered.jsonl"
INPUT_JUDGMENTS = "fragments/llm_judgments.jsonl"

# 出力ファイル（人間が査読するためのマージされた一時ファイル）
OUTPUT_MERGED = "fragments/merged_for_verification.jsonl"
# ======================================

def get_id(data):
    for key in ['id', '@id', 'uri', 'url']:
        if key in data:
            return data[key]
    return None

def main():
    if not os.path.exists(INPUT_JUDGMENTS):
        print(f"判定結果ファイルが見つかりません: {INPUT_JUDGMENTS}")
        return
    if not os.path.exists(INPUT_ORIGINAL):
        print(f"元データファイルが見つかりません: {INPUT_ORIGINAL}")
        return

    # 1. LLM判定結果を読み込んで辞書化 (ID -> 判定データ)
    judgments = {}
    with open(INPUT_JUDGMENTS, 'r', encoding='utf-8') as f:
        for line in f:
            try:
                row = json.loads(line)
                jid = get_id(row)
                if jid:
                    judgments[jid] = row
            except json.JSONDecodeError:
                continue

    print(f"読み込んだ判定結果: {len(judgments)} 件")

    merged_count = 0
    # 2. 元データを走査し、判定結果が存在するものだけをマージして出力
    # (※本番運用時は、判定結果があるものだけ、もしくは全データを対象に出力するように調整可能)
    with open(INPUT_ORIGINAL, 'r', encoding='utf-8') as fin, \
         open(OUTPUT_MERGED, 'w', encoding='utf-8') as fout:
        
        for line in fin:
            try:
                original_data = json.loads(line)
                oid = get_id(original_data)
                
                if oid and oid in judgments:
                    judg = judgments[oid]
                    
                    # 統合メタデータオブジェクトを作成
                    original_data["_inferred_metadata"] = {
                        "is_score": judg.get("judgment"), # true/false/null
                        "genre": None,                    # プレースホルダー
                        "instruments": [],                # プレースホルダー
                        
                        "_evidence": {
                            "score_reason": judg.get("reason", ""),
                            "stage": judg.get("stage", "unknown"),
                            "retrieved_web_snippets": [] # 必要に応じて後段でスニペットを格納
                        }
                    }
                    
                    fout.write(json.dumps(original_data, ensure_ascii=False) + "\n")
                    merged_count += 1
            except json.JSONDecodeError:
                continue

    print(f"✅ マージ完了！ {merged_count} 件のデータを {OUTPUT_MERGED} に出力しました。")

if __name__ == "__main__":
    main()
