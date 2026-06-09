import pandas as pd
import json
import re
from collections import Counter
import os

# =================設定=================
INPUT_JSONL = "./data/classical_scores_dynamic.jsonl"
TOP_N = 1000
# ======================================

def extract_fu_compounds(text):
    """
    テキスト内から「譜」で終わる単語を抽出する
    改良点: 漢字だけでなく、カタカナ（ピアノ譜など）も含める
    """
    if not isinstance(text, str):
        return []
    
    # [一-龠々]: 漢字
    # [ァ-ヶー]: カタカナ（長音含む）
    # + : 1文字以上続く
    # 譜 : 最後に譜がつく
    matches = re.findall(r'([一-龠々ァ-ヶー]+譜)', text)
    return matches

def main():
    if not os.path.exists(INPUT_JSONL):
        print(f"File not found: {INPUT_JSONL}")
        return

    print("データをスキャンして「〇〇譜」を収集中...")
    
    all_compounds = []
    
    with open(INPUT_JSONL, 'r', encoding='utf-8') as f:
        for line in f:
            try:
                data = json.loads(line)
                
                # タイトル(label/name)を対象にする
                title = data.get('rdfs:label', '') or data.get('schema:name', '') or ''
                
                # タイトルの途中にある「〇〇譜」もすべて抽出
                compounds = extract_fu_compounds(title)
                all_compounds.extend(compounds)
                
            except json.JSONDecodeError:
                continue

    # 集計
    counter = Counter(all_compounds)
    
    print(f"\n=== 「〇〇譜」頻出ランキング (Top {TOP_N}) ===")
    print(f"{'順位':<5} | {'単語':<20} | {'回数':<5}")
    print("-" * 40)
    
    rank = 1
    for word, count in counter.most_common(TOP_N):
        # あまりに長いヒット（文章ごと取れてしまったものなど）はノイズとして視認しやすくするため
        # 15文字以内で表示調整
        display_word = (word[:15] + '..') if len(word) > 15 else word
        print(f"{rank:<5} | {display_word:<20} | {count:<5}")
        rank += 1

    # CSV保存
    output_vocab = "./data/vocab_ranking.csv"
    pd.DataFrame(counter.most_common(), columns=['Word', 'Count']).to_csv(output_vocab, index=False, encoding='utf-8-sig')
    print(f"\n保存完了: {output_vocab}")

if __name__ == "__main__":
    main()