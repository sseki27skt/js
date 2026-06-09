import pandas as pd
import json
import re
import os
from collections import Counter, defaultdict

# =================設定=================
INPUT_JSONL = "fragments/classical_scores_fu_filtered3.jsonl"
# 保存先フォルダ（なければ作る）
OUTPUT_DIR = "fragments/ngram"
OUTPUT_CSV = f"{OUTPUT_DIR}/keyword_mining_ranking.csv"
OUTPUT_SAMPLES = f"{OUTPUT_DIR}/keyword_samples.json" # ★追加：サンプル保存用
TOP_N = 200 
MAX_SAMPLES = 10 # ★追加：1つの単語につき保存する例文の最大数
# ======================================

def generate_ngrams(text, n):
    """記号を除去してN-gramを生成"""
    text = re.sub(r'[ 　\(\)（）\[\]「」『』\.,]', '', str(text))
    if len(text) < n:
        return []
    return [text[i:i+n] for i in range(len(text)-n+1)]

def main():
    if not os.path.exists(INPUT_JSONL):
        print(f"入力ファイルが見つかりません: {INPUT_JSONL}")
        return

    # 出力ディレクトリ作成
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    print("データ分析とサンプル抽出を実行中...")

    # カウンターとサンプル集め用辞書
    counts = {2: Counter(), 3: Counter(), 4: Counter(), 5: Counter()}
    samples = {2: defaultdict(list), 3: defaultdict(list), 4: defaultdict(list), 5: defaultdict(list)}
    
    data_count = 0

    with open(INPUT_JSONL, 'r', encoding='utf-8') as f:
        for line in f:
            try:
                data = json.loads(line)
                data_count += 1
                
                label = data.get('rdfs:label')
                name = data.get('schema:name')
                title = str(label) if label else (str(name) if name else "")
                
                if not title: continue

                # 各N-gramサイズについて処理
                for n in [2, 3, 4, 5]:
                    ngrams = generate_ngrams(title, n)
                    counts[n].update(ngrams)
                    
                    # サンプル収集（まだ上限に達していない場合のみ追加）
                    for word in ngrams:
                        if len(samples[n][word]) < MAX_SAMPLES:
                            # 同じタイトルが重複しないようにチェック
                            if title not in samples[n][word]:
                                samples[n][word].append(title)
                
            except json.JSONDecodeError:
                continue

    print(f"分析対象: {data_count}件")
    print("ランキング作成中...")

    results = []
    
    # 頻出上位を取得し、結果リストを作成
    # 各Nについて上位TOP_N個を取得
    top_lists = {n: counts[n].most_common(TOP_N) for n in [2, 3, 4, 5]}
    
    # まとめてCSV用の形式にする
    for i in range(TOP_N):
        row = {"Rank": i+1}
        for n in [2, 3, 4, 5]:
            word, count = top_lists[n][i] if i < len(top_lists[n]) else ("", "")
            
            # 列名定義 (例: Bi-gram, Bi-Count)
            prefix = {2: "Bi", 3: "Tri", 4: "Tetra", 5: "Penta"}[n]
            row[f"{prefix}-gram"] = word
            row[f"{prefix}-Count"] = count
        
        results.append(row)

    # 1. ランキングCSV保存
    pd.DataFrame(results).to_csv(OUTPUT_CSV, index=False, encoding='utf-8-sig')

    # 2. サンプルデータのJSON保存（アプリ側で使うため）
    # 階層構造: { "2": {"単語A": ["例1", "例2"], ...}, "3": ... }
    # JSON化のためにdefaultdictをdictに戻す
    final_samples = {}
    for n in [2, 3, 4, 5]:
        # TOP_Nに入った単語のサンプルだけを保存してファイルサイズ削減
        target_words = set(w for w, c in top_lists[n])
        final_samples[str(n)] = {k: v for k, v in samples[n].items() if k in target_words}

    with open(OUTPUT_SAMPLES, 'w', encoding='utf-8') as f:
        json.dump(final_samples, f, ensure_ascii=False, indent=2)

    print(f"完了しました。\nCSV: {OUTPUT_CSV}\nSamples: {OUTPUT_SAMPLES}")

if __name__ == "__main__":
    main()