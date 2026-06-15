# -*- coding: utf-8 -*-
import pandas as pd
import json
import re
import os
from collections import Counter, defaultdict

# ----------------- N-gram集計 -----------------

def generate_ngrams(text, n):
    """記号を除去してN-gramを生成"""
    text = re.sub(r'[ 　\(\)（）\[\]「」『』\.,]', '', str(text))
    if len(text) < n:
        return []
    return [text[i:i+n] for i in range(len(text)-n+1)]

def run_ngram_analysis(input_jsonl, output_csv, output_samples_json, top_n=200):
    """
    データから 2,3,4,5-gram の出現頻度を分析し、
    ランキングCSVとサンプル文（出現元タイトル）を紐づけたJSONを出力します。
    """
    if not os.path.exists(input_jsonl):
        raise FileNotFoundError(f"入力ファイルが見つかりません: {input_jsonl}")

    counts = {2: Counter(), 3: Counter(), 4: Counter(), 5: Counter()}
    samples = {2: defaultdict(list), 3: defaultdict(list), 4: defaultdict(list), 5: defaultdict(list)}
    
    data_count = 0

    with open(input_jsonl, 'r', encoding='utf-8') as f:
        for line in f:
            try:
                data = json.loads(line)
                data_count += 1
                
                label = data.get('rdfs:label')
                name = data.get('schema:name')
                title = str(label) if label else (str(name) if name else "")
                
                if not title: 
                    continue

                for n in [2, 3, 4, 5]:
                    ngrams = generate_ngrams(title, n)
                    counts[n].update(ngrams)
                    
                    for word in ngrams:
                        if title not in samples[n][word]:
                            samples[n][word].append(title)
            except json.JSONDecodeError:
                continue

    # ランキングCSV作成
    top_lists = {n: counts[n].most_common(top_n) for n in [2, 3, 4, 5]}
    results = []
    
    for i in range(top_n):
        row = {"Rank": i+1}
        for n in [2, 3, 4, 5]:
            word, count = top_lists[n][i] if i < len(top_lists[n]) else ("", "")
            prefix = {2: "Bi", 3: "Tri", 4: "Tetra", 5: "Penta"}[n]
            row[f"{prefix}-gram"] = word
            row[f"{prefix}-Count"] = count
        results.append(row)

    # 保存
    os.makedirs(os.path.dirname(output_csv), exist_ok=True)
    pd.DataFrame(results).to_csv(output_csv, index=False, encoding='utf-8-sig')

    # サンプルデータのJSON保存（ファイルサイズ削減のためTOP_Nの語彙に限定）
    final_samples = {}
    for n in [2, 3, 4, 5]:
        target_words = set(w for w, c in top_lists[n])
        final_samples[str(n)] = {k: v for k, v in samples[n].items() if k in target_words}

    os.makedirs(os.path.dirname(output_samples_json), exist_ok=True)
    with open(output_samples_json, 'w', encoding='utf-8') as f:
        json.dump(final_samples, f, ensure_ascii=False, indent=2)

    return data_count

# ----------------- OK/NG/Gray 3分割 -----------------

def load_word_list(path):
    if os.path.exists(path):
        with open(path, 'r', encoding='utf-8') as f:
            return [line.strip() for line in f if line.strip()]
    return []

def run_data_split(input_jsonl, ok_list_path, ng_list_path, out_ok_jsonl, out_ng_jsonl, out_gray_jsonl):
    """
    OKワード/NGワードリストに基づき、データを確定OK、確定NG、グレー（LLM用）の3つに分割します。
    """
    if not os.path.exists(input_jsonl):
        raise FileNotFoundError(f"入力ファイルが見つかりません: {input_jsonl}")

    ng_words = load_word_list(ng_list_path)
    ok_words = load_word_list(ok_list_path)
    
    counts = {"ok": 0, "ng": 0, "gray": 0}

    os.makedirs(os.path.dirname(out_ok_jsonl), exist_ok=True)
    os.makedirs(os.path.dirname(out_ng_jsonl), exist_ok=True)
    os.makedirs(os.path.dirname(out_gray_jsonl), exist_ok=True)

    with open(input_jsonl, 'r', encoding='utf-8') as fin, \
         open(out_ok_jsonl, 'w', encoding='utf-8') as f_ok, \
         open(out_ng_jsonl, 'w', encoding='utf-8') as f_ng, \
         open(out_gray_jsonl, 'w', encoding='utf-8') as f_gray:

        for line in fin:
            try:
                data = json.loads(line)
                
                label = data.get('rdfs:label')
                name = data.get('schema:name')
                title = str(label) if label else (str(name) if name else "")
                
                # 1. まずNG判定（NGが含まれていたら即除外）
                hit_ng = next((w for w in ng_words if w in title), None)
                if hit_ng:
                    counts["ng"] += 1
                    data["_filter_reason"] = f"NG: {hit_ng}"
                    f_ng.write(json.dumps(data, ensure_ascii=False) + "\n")
                    continue

                # 2. 次にOK判定
                hit_ok = next((w for w in ok_words if w in title), None)
                if hit_ok:
                    counts["ok"] += 1
                    data["_filter_reason"] = f"OK: {hit_ok}"
                    data["is_score"] = True 
                    f_ok.write(json.dumps(data, ensure_ascii=False) + "\n")
                    continue

                # 3. 残りはグレーゾーン（LLM行き）
                counts["gray"] += 1
                f_gray.write(line)
            except json.JSONDecodeError:
                continue

    return counts
