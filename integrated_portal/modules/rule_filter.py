# -*- coding: utf-8 -*-
import pandas as pd
import json
import re
import os
import csv
from collections import Counter, defaultdict

# ----------------- About フィルタ関数 -----------------

def extract_searchable_text(row):
    """
    判定対象となるテキストを抽出・結合する関数。
    タイトル(rdfs:label/schema:name) と schema:about の中身を結合。
    """
    label = row.get('rdfs:label')
    name = row.get('schema:name')
    title = str(label) if label else (str(name) if name else "")
    
    about_text = ""
    about_data = row.get('schema:about')
    if about_data:
        about_text = json.dumps(about_data, ensure_ascii=False)
    
    return f"{title} ||| {about_text}"

def run_about_filter(input_jsonl, output_jsonl, output_discarded_csv, output_suffix_csv, output_samples_json, rules_file):
    """
    About ルール (about_rules.json) を用いてデータをフィルタリングし、
    合格データを出力。さらに合格データから「〜譜」接尾辞の集計とサンプルを生成します。
    """
    if not os.path.exists(input_jsonl):
        raise FileNotFoundError(f"入力ファイルが見つかりません: {input_jsonl}")

    # ルール読み込み
    noise_patterns = []
    strong_keywords = []
    if os.path.exists(rules_file):
        try:
            with open(rules_file, 'r', encoding='utf-8') as f:
                rules_data = json.load(f)
                noise_patterns = rules_data.get("NOISE_PATTERNS", [])
                strong_keywords = rules_data.get("STRONG_KEYWORDS", [])
        except Exception as e:
            print(f"⚠️ ルールファイルの読み込みエラー: {e}")

    # 正規表現コンパイル
    white_regex = re.compile("|".join(map(re.escape, strong_keywords))) if strong_keywords else None
    black_regex = re.compile("|".join(map(re.escape, noise_patterns))) if noise_patterns else None

    keep_list = []
    discard_list = []
    
    saved_by_whitelist = 0
    dropped_by_blacklist = 0

    with open(input_jsonl, 'r', encoding='utf-8') as f:
        for line in f:
            try:
                row = json.loads(line)
                search_text = extract_searchable_text(row)
                
                # 1. ホワイトリスト判定
                if white_regex and white_regex.search(search_text):
                    keep_list.append(row)
                    if black_regex and black_regex.search(search_text):
                        saved_by_whitelist += 1
                    continue

                # 2. ブラックリスト判定
                if black_regex:
                    match = black_regex.search(search_text)
                    if match:
                        row['exclusion_reason'] = f"NG Hit: {match.group()}"
                        discard_list.append(row)
                        dropped_by_blacklist += 1
                        continue

                # 3. どちらにも該当しない
                keep_list.append(row)
            except json.JSONDecodeError:
                continue

    # 保存
    os.makedirs(os.path.dirname(output_jsonl), exist_ok=True)
    with open(output_jsonl, 'w', encoding='utf-8') as f:
        for item in keep_list:
            f.write(json.dumps(item, ensure_ascii=False) + '\n')

    # 除外リスト(CSV)出力
    if discard_list:
        os.makedirs(os.path.dirname(output_discarded_csv), exist_ok=True)
        df_discard = pd.DataFrame(discard_list)
        cols = ['exclusion_reason', 'rdfs:label', 'schema:name']
        valid_cols = [c for c in cols if c in df_discard.columns]
        other_cols = [c for c in df_discard.columns if c not in valid_cols]
        df_discard[valid_cols + other_cols].to_csv(
            output_discarded_csv, 
            index=False, 
            encoding='utf-8-sig',
            quoting=csv.QUOTE_ALL
        )

    # 接尾辞(〜譜)の集計・サンプル生成 (合格データから)
    if keep_list:
        all_suffixes = []
        sample_map = defaultdict(list)
        MAX_SAMPLES = 50  # 最大サンプル数を50件に拡大
        MAX_SUFFIX_LEN = 9

        for row in keep_list:
            label = row.get('rdfs:label')
            name = row.get('schema:name')
            title = str(label) if label else (str(name) if name else "")
            if not title:
                continue

            # ひらがなや英数字も含めて「〜譜」を抽出するように拡張
            matches = re.findall(r'([ぁ-ん一-龠々ァ-ヶーa-zA-Z0-9]+譜)', title)
            unique_suffixes = set()
            for word in matches:
                suffix_row = {"Full": word}
                for i in range(2, MAX_SUFFIX_LEN + 1):
                    suffix_row[f"Last{i}"] = word[-i:] if len(word) >= i else None
                all_suffixes.append(suffix_row)

                for i in range(2, MAX_SUFFIX_LEN + 1):
                    if len(word) >= i:
                        unique_suffixes.add(word[-i:])

            for s in unique_suffixes:
                if len(sample_map[s]) < MAX_SAMPLES:
                    if title not in sample_map[s]:
                        sample_map[s].append(title)

        # CSVランキング構築
        rank_data = {}
        max_len = 0
        for i in range(2, MAX_SUFFIX_LEN + 1):
            key = f"Last{i}"
            words = [x[key] for x in all_suffixes if x.get(key)]
            counter = Counter(words).most_common()
            rank_data[key] = counter
            if len(counter) > max_len:
                max_len = len(counter)

        csv_rows = []
        for i in range(max_len):
            csv_row = {"Rank": i + 1}
            for j in range(2, MAX_SUFFIX_LEN + 1):
                key = f"Last{j}"
                data_list = rank_data[key]
                if i < len(data_list):
                    word, count = data_list[i]
                    csv_row[f"{key} ({j-1}字+譜)"] = f"{word} ({count})"
                else:
                    csv_row[f"{key} ({j-1}字+譜)"] = ""
            csv_rows.append(csv_row)

        os.makedirs(os.path.dirname(output_suffix_csv), exist_ok=True)
        df_suffix = pd.DataFrame(csv_rows)
        df_suffix.to_csv(output_suffix_csv, index=False, encoding='utf-8-sig')

        # サンプルJSON保存
        os.makedirs(os.path.dirname(output_samples_json), exist_ok=True)
        with open(output_samples_json, 'w', encoding='utf-8') as f:
            json.dump(sample_map, f, ensure_ascii=False, indent=2)

    return len(keep_list), len(discard_list)


# ----------------- Suffix フィルタ関数 -----------------

def run_suffix_filter(input_jsonl, output_jsonl, output_discarded_csv, rules_file):
    """
    Suffix ルール (suffix_rules.json) を用いてデータをフィルタリングし、
    合格データを出力します。
    """
    if not os.path.exists(input_jsonl):
        raise FileNotFoundError(f"入力ファイルが見つかりません: {input_jsonl}")

    # ルール読み込み
    noise_patterns = []
    if os.path.exists(rules_file):
        try:
            with open(rules_file, 'r', encoding='utf-8') as f:
                rules_data = json.load(f)
                noise_patterns = rules_data.get("NOISE_PATTERNS", [])
        except Exception as e:
            print(f"⚠️ ルールファイルの読み込みエラー: {e}")

    if not noise_patterns:
        # パターンがない場合は、単に全コピーして終了
        shutil.copy2(input_jsonl, output_jsonl)
        return sum(1 for _ in open(input_jsonl, 'r', encoding='utf-8')), 0

    pattern_regex = re.compile("|".join(map(re.escape, noise_patterns)))

    keep_list = []
    discard_list = []

    with open(input_jsonl, 'r', encoding='utf-8') as f:
        for line in f:
            try:
                row = json.loads(line)
                label = row.get('rdfs:label')
                name = row.get('schema:name')
                title = str(label) if label else (str(name) if name else "")
                
                if not title:
                    keep_list.append(row)
                    continue

                match = pattern_regex.search(title)
                if match:
                    row['exclusion_reason'] = f"Suffix NG: {match.group()}"
                    discard_list.append(row)
                else:
                    keep_list.append(row)
            except json.JSONDecodeError:
                continue

    # 保存
    os.makedirs(os.path.dirname(output_jsonl), exist_ok=True)
    with open(output_jsonl, 'w', encoding='utf-8') as f:
        for item in keep_list:
            f.write(json.dumps(item, ensure_ascii=False) + '\n')

    # 除外リスト(CSV)出力
    if discard_list:
        os.makedirs(os.path.dirname(output_discarded_csv), exist_ok=True)
        df_discard = pd.DataFrame(discard_list)
        cols = ['exclusion_reason', 'rdfs:label', 'schema:name']
        valid_cols = [c for c in cols if c in df_discard.columns]
        other_cols = [c for c in df_discard.columns if c not in valid_cols]
        df_discard[valid_cols + other_cols].to_csv(
            output_discarded_csv, 
            index=False, 
            encoding='utf-8-sig',
            quoting=csv.QUOTE_ALL
        )

    import shutil # 必要時のインポート

    return len(keep_list), len(discard_list)
