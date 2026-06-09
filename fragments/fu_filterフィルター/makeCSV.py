import pandas as pd
import json
import re
import os
from collections import Counter

# =================設定=================
# INPUT_JSONL = "./fragments/classical_scores_about_filtered.jsonl"
INPUT_JSONL = "./fragments/classical_scores_fu_filtered.jsonl"
OUTPUT_SUFFIX_RANK = "./fragments/suffix_analysis_extended.csv"
MAX_SUFFIX_LEN = 9 # Last9まで
# ======================================

def extract_suffixes(text):
    if not isinstance(text, str): return []
    matches = re.findall(r'([一-龠々ァ-ヶー]+譜)', text)
    suffixes = []
    for word in matches:
        row = {"Full": word}
        # Last2 ~ Last9
        for i in range(2, MAX_SUFFIX_LEN + 1):
            key = f"Last{i}"
            row[key] = word[-i:] if len(word) >= i else None
        suffixes.append(row)
    return suffixes

def main():
    if not os.path.exists(INPUT_JSONL):
        print(f"ファイルが見つかりません: {INPUT_JSONL}")
        return

    print(f"全量データ抽出中（最大{MAX_SUFFIX_LEN-1}文字+譜）...")
    
    all_suffixes = []
    
    with open(INPUT_JSONL, 'r', encoding='utf-8') as f:
        for line in f:
            try:
                data = json.loads(line)
                label = data.get('rdfs:label')
                name = data.get('schema:name')
                title = str(label) if label else (str(name) if name else "")
                
                if not title: continue
                
                all_suffixes.extend(extract_suffixes(title))
                
            except json.JSONDecodeError:
                continue

    # 集計
    rank_data = {}
    max_len = 0
    
    # 各Lastごとに全量を集計
    for i in range(2, MAX_SUFFIX_LEN + 1):
        key = f"Last{i}"
        words = [x[key] for x in all_suffixes if x.get(key)]
        # 全量取得 (most_commonに引数を渡さない)
        counter = Counter(words).most_common() 
        
        rank_data[key] = counter
        if len(counter) > max_len:
            max_len = len(counter)

    print(f"最大行数: {max_len} 件のデータを構築します...")

    # DataFrame構築用のリストを作成
    # 長さが不揃いなので、最大長に合わせて空文字で埋める
    csv_rows = []
    for i in range(max_len):
        row = {"Rank": i + 1}
        for j in range(2, MAX_SUFFIX_LEN + 1):
            key = f"Last{j}"
            data_list = rank_data[key]
            
            if i < len(data_list):
                word, count = data_list[i]
                row[f"{key} ({j-1}字+譜)"] = f"{word} ({count})"
            else:
                row[f"{key} ({j-1}字+譜)"] = ""
        csv_rows.append(row)

    df = pd.DataFrame(csv_rows)
    df.to_csv(OUTPUT_SUFFIX_RANK, index=False, encoding='utf-8-sig')
    
    print(f"\n保存完了: {OUTPUT_SUFFIX_RANK}")
    print("件数制限なしのCSVを作成しました。")

if __name__ == "__main__":
    main()