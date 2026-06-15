import pandas as pd
import json
import re
import os
import csv

# =================設定=================
INPUT_JSONL = "./data/classical_scores_dynamic.jsonl"
OUTPUT_JSONL = "./data/classical_scores_about_filtered.jsonl"
OUTPUT_DISCARDED_CSV = "./data/discarded.csv"
OUTPUT_SUFFIX_RANK = "./data/suffix_analysis_extended.csv"
OUTPUT_SAMPLES = "./data/suffix_samples.json"
RULES_FILE = "./02_rule_based_filtering/about_rules.json"
# ======================================

# 外部のルールファイルからブラックリスト・ホワイトリストを読み込む
NOISE_PATTERNS = []
STRONG_KEYWORDS = []

if os.path.exists(RULES_FILE):
    try:
        with open(RULES_FILE, 'r', encoding='utf-8') as f_rules:
            rules_data = json.load(f_rules)
            NOISE_PATTERNS = rules_data.get("NOISE_PATTERNS", [])
            STRONG_KEYWORDS = rules_data.get("STRONG_KEYWORDS", [])
    except Exception as e:
        print(f"⚠️ ルールファイルの読み込みに失敗しました: {e}")
else:
    print(f"⚠️ ルールファイルが見つかりません: {RULES_FILE}")

def extract_searchable_text(row):
    """
    判定対象となるテキストを抽出・結合する関数。
    タイトル(rdfs:label/schema:name) と schema:about の中身を
    1つの長い文字列にして、検索漏れを防ぎます。
    """
    # 1. タイトル
    label = row.get('rdfs:label')
    name = row.get('schema:name')
    title = str(label) if label else (str(name) if name else "")
    
    # 2. About情報 (URIやキーワード)
    about_text = ""
    about_data = row.get('schema:about')
    
    if about_data:
        # 簡易的にJSON文字列化して、その中のすべての文字を検索対象にする
        # (構造を再帰的に掘るより高速で、キーワード検索には十分なため)
        about_text = json.dumps(about_data, ensure_ascii=False)
    
    # 結合して返す (区切り文字を入れておく)
    return f"{title} ||| {about_text}"

def main():
    if not os.path.exists(INPUT_JSONL):
        print(f"ファイルが見つかりません: {INPUT_JSONL}")
        return

    print("最終フィルタリングを開始します...")
    print(f"・ホワイトリスト (優先): {len(STRONG_KEYWORDS)}件")
    print(f"・ブラックリスト (除外): {len(NOISE_PATTERNS)}件")

    # 正規表現コンパイル
    white_regex = None
    if STRONG_KEYWORDS:
        white_regex = re.compile("|".join(map(re.escape, STRONG_KEYWORDS)))
        
    black_regex = None
    if NOISE_PATTERNS:
        black_regex = re.compile("|".join(map(re.escape, NOISE_PATTERNS)))

    keep_list = []
    discard_list = []
    
    saved_by_whitelist = 0
    dropped_by_blacklist = 0

    with open(INPUT_JSONL, 'r', encoding='utf-8') as f:
        for line in f:
            try:
                row = json.loads(line)
                
                # 判定用のテキストを作成（タイトル + About情報）
                search_text = extract_searchable_text(row)
                
                # --- 判定ロジック ---
                
                # 1. ホワイトリスト判定 (最優先)
                if white_regex and white_regex.search(search_text):
                    # ヒットしたら即採用
                    keep_list.append(row)
                    
                    # (統計用) もしブラックリストにも入っていたら「救済された」とカウント
                    if black_regex and black_regex.search(search_text):
                        saved_by_whitelist += 1
                    continue

                # 2. ブラックリスト判定
                if black_regex:
                    match = black_regex.search(search_text)
                    if match:
                        # ヒットしたら除外
                        row['exclusion_reason'] = f"NG Hit: {match.group()}"
                        discard_list.append(row)
                        dropped_by_blacklist += 1
                        continue

                # 3. どちらにも該当しない -> 採用
                keep_list.append(row)

            except json.JSONDecodeError:
                continue

    # === 結果保存 ===
    
    # JSONL出力
    if keep_list:
        with open(OUTPUT_JSONL, 'w', encoding='utf-8') as f:
            for item in keep_list:
                f.write(json.dumps(item, ensure_ascii=False) + '\n')
        print(f"\n✅ [完成] 最終データ: {len(keep_list)}件 -> {OUTPUT_JSONL}")
    else:
        print("\n⚠️ データが1件も残りませんでした。")

    # 統計情報の表示
    print(f"   - ホワイトリストによる救済（NG回避）: {saved_by_whitelist}件")
    print(f"   - ブラックリストによる除外: {dropped_by_blacklist}件")

    # 除外リスト(CSV)出力
    if discard_list:
        df_discard = pd.DataFrame(discard_list)
        cols = ['exclusion_reason', 'rdfs:label', 'schema:name']
        valid_cols = [c for c in cols if c in df_discard.columns]
        other_cols = [c for c in df_discard.columns if c not in valid_cols]
        
        df_discard[valid_cols + other_cols].to_csv(
            OUTPUT_DISCARDED_CSV, 
            index=False, 
            encoding='utf-8-sig',
            quoting=csv.QUOTE_ALL
        )
        print(f"🗑️ [除外] 除外データ一覧: {OUTPUT_DISCARDED_CSV}")

    # === [統合処理] 接尾辞(〜譜)の集計・サンプル生成 ===
    if keep_list:
        print("\n📊 合格データから「〜譜」接尾辞の集計とサンプル生成を開始します...")
        from collections import Counter, defaultdict

        all_suffixes = []
        sample_map = defaultdict(list)
        MAX_SAMPLES = 20
        MAX_SUFFIX_LEN = 9

        for row in keep_list:
            label = row.get('rdfs:label')
            name = row.get('schema:name')
            title = str(label) if label else (str(name) if name else "")
            if not title:
                continue

            # 1. サンプル抽出用
            matches = re.findall(r'([一-龠々ァ-ヶー]+譜)', title)
            unique_suffixes = set()
            for word in matches:
                # CSV集計用データの作成
                suffix_row = {"Full": word}
                for i in range(2, MAX_SUFFIX_LEN + 1):
                    suffix_row[f"Last{i}"] = word[-i:] if len(word) >= i else None
                all_suffixes.append(suffix_row)

                # サンプル用
                for i in range(2, MAX_SUFFIX_LEN + 1):
                    if len(word) >= i:
                        unique_suffixes.add(word[-i:])

            # サンプル対応マップの構築
            for s in unique_suffixes:
                if len(sample_map[s]) < MAX_SAMPLES:
                    if title not in sample_map[s]:
                        sample_map[s].append(title)

        # --- CSVデータの構築・保存 ---
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

        df_suffix = pd.DataFrame(csv_rows)
        df_suffix.to_csv(OUTPUT_SUFFIX_RANK, index=False, encoding='utf-8-sig')
        print(f"  -> CSVランキング保存完了: {OUTPUT_SUFFIX_RANK}")

        # --- JSONサンプルの保存 ---
        with open(OUTPUT_SAMPLES, 'w', encoding='utf-8') as f_sample:
            json.dump(sample_map, f_sample, ensure_ascii=False, indent=2)
        print(f"  -> サンプルJSON保存完了: {OUTPUT_SAMPLES}")

if __name__ == "__main__":
    main()