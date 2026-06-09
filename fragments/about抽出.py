import pandas as pd
import json
import os
from collections import Counter

# =================設定=================
INPUT_JSONL = "fragments/classical_scores_fu_filtered.jsonl"
OUTPUT_ABOUT_RANK = "./fragments/about_keywords_ranking.csv"
TOP_N_DISPLAY = 50 # コンソール表示用の上限
# ======================================

def extract_values_robust(obj):
    """
    schema:about からキーワードを「漏れなく」抽出する関数
    修正点: elifをやめてifを並列にし、URI(@id)と名称(name/label)の両方を取得する
    """
    values = []
    
    if isinstance(obj, str):
        values.append(obj)
        
    elif isinstance(obj, list):
        for item in obj:
            values.extend(extract_values_robust(item))
            
    elif isinstance(obj, dict):
        # 1. URI (@id) があれば必ず取得
        if '@id' in obj:
            values.append(obj['@id'])
            
        # 2. 名称 (name, schema:name) があれば取得
        if 'name' in obj:
            values.extend(extract_values_robust(obj['name']))
        elif 'schema:name' in obj:
            values.extend(extract_values_robust(obj['schema:name']))
            
        # 3. ラベル (rdfs:label) があれば取得
        if 'rdfs:label' in obj:
            values.extend(extract_values_robust(obj['rdfs:label']))
            
        # 4. 値 (@value) があれば取得 (稀なケース)
        if '@value' in obj:
            values.append(obj['@value'])
            
    return values

def main():
    if not os.path.exists(INPUT_JSONL):
        print(f"ファイルが見つかりません: {INPUT_JSONL}")
        return

    print("schema:about の全項目抽出を開始します...")
    
    all_keywords = []
    data_count = 0
    has_about_count = 0

    with open(INPUT_JSONL, 'r', encoding='utf-8') as f:
        for line in f:
            try:
                data = json.loads(line)
                data_count += 1
                
                about_data = data.get('schema:about')
                
                if about_data:
                    has_about_count += 1
                    # 修正した関数を使用
                    keywords = extract_values_robust(about_data)
                    all_keywords.extend(keywords)
                    
            except json.JSONDecodeError:
                continue

    # 集計
    counter = Counter(all_keywords)
    
    print(f"総データ数: {data_count}件")
    print(f"schema:about を持つデータ: {has_about_count}件")
    print(f"抽出されたキーワード総数(延べ): {len(all_keywords)}")
    print(f"ユニークキーワード数: {len(counter)}")

    # 結果表示（コンソールには上位のみ）
    print(f"\n=== schema:about 頻出キーワード (Top {TOP_N_DISPLAY}) ===")
    print(f"{'順位':<5} | {'キーワード/URI':<50} | {'回数':<5}")
    print("-" * 70)
    
    results = []
    # 全件ループしてリスト化
    for i, (word, count) in enumerate(counter.most_common()):
        results.append({"Rank": i+1, "Keyword": word, "Count": count})
        
        if i < TOP_N_DISPLAY:
            display_word = (word[:47] + '...') if len(word) > 50 else word
            print(f"{i+1:<5} | {display_word:<50} | {count:<5}")

    # CSV保存（全件保存）
    df = pd.DataFrame(results)
    df.to_csv(OUTPUT_ABOUT_RANK, index=False, encoding='utf-8-sig')
    print(f"\n保存完了: {OUTPUT_ABOUT_RANK}")
    print("今回は全件出力していますので、Excel等で検索してハワイ大学のURIなどが含まれているか確認してください。")

if __name__ == "__main__":
    main()