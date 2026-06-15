import json
import re
import os
from collections import defaultdict

# =================設定=================
# 入力ファイル（フィルタリング済みの中間ファイル推奨）
# INPUT_JSONL = "./fragments/classical_scores_about_filtered.jsonl"
INPUT_JSONL = "./fragments/classical_scores_fu_filtered.jsonl"
# 出力ファイル
OUTPUT_SAMPLES = "./fragments/suffix_samples.json"

# ★ここを変更しました
MAX_SAMPLES = 20   # 1単語あたりのサンプル表示数（5 -> 20に増量）
MAX_SUFFIX_LEN = 9 # Last9まで対応
# ======================================

def extract_suffixes(text):
    """テキストからLast2~Last9の接尾辞を抽出"""
    if not isinstance(text, str): return []
    matches = re.findall(r'([一-龠々ァ-ヶー]+譜)', text)
    suffixes = []
    for word in matches:
        # Last2 ~ Last9
        for i in range(2, MAX_SUFFIX_LEN + 1):
            if len(word) >= i:
                suffixes.append(word[-i:])
    return set(suffixes)

def main():
    if not os.path.exists(INPUT_JSONL):
        print(f"ファイルがありません: {INPUT_JSONL}")
        return

    print(f"サンプルデータを抽出中 (Max {MAX_SAMPLES}件)...")
    
    # { "家譜": ["徳川家譜", "織田家譜"...], ... }
    sample_map = defaultdict(list)
    
    with open(INPUT_JSONL, 'r', encoding='utf-8') as f:
        for line in f:
            try:
                row = json.loads(line)
                label = row.get('rdfs:label') or row.get('schema:name') or ""
                title = str(label)
                if not title: continue
                
                suffixes = extract_suffixes(title)
                
                for s in suffixes:
                    # まだ上限に達していなければ追加
                    if len(sample_map[s]) < MAX_SAMPLES:
                        # 重複タイトルは除外
                        if title not in sample_map[s]:
                            sample_map[s].append(title)
            except:
                continue

    # 保存
    with open(OUTPUT_SAMPLES, 'w', encoding='utf-8') as f:
        json.dump(sample_map, f, ensure_ascii=False, indent=2)
        
    print(f"完了: {OUTPUT_SAMPLES}")
    print("アプリをリロード（Rerun）すると、ツールチップの事例が増えています。")

if __name__ == "__main__":
    main()