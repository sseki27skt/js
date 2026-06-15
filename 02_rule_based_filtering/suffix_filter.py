# -*- coding: utf-8 -*-
import pandas as pd
import json
import re
import os
import csv

# =================設定=================
# 入力: schema:about でのフィルタリングを通過したファイル
INPUT_JSONL = "./data/classical_scores_about_filtered.jsonl"

# 出力: 完成した最終データ
OUTPUT_FINAL_JSONL = "./data/classical_scores_suffix_filtered.jsonl"

# 確認用: 除外されたデータのリスト
OUTPUT_DISCARDED_CSV = "./data/discarded_suffix_filtered.csv"

# ルール定義ファイル
RULES_FILE = "./02_rule_based_filtering/suffix_rules.json"
# ======================================

def load_rules():
    """suffix_rules.json からNGパターンリストを読み込む"""
    rules = []
    if os.path.exists(RULES_FILE):
        try:
            with open(RULES_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                rules = data.get("NOISE_PATTERNS", [])
        except Exception as e:
            print(f"⚠️ ルールファイルの読み込みエラー: {e}")
    else:
        print(f"⚠️ ルールファイルが見つかりません: {RULES_FILE}")
    return rules

def main():
    # 1. ファイルチェック
    if not os.path.exists(INPUT_JSONL):
        print(f"エラー: 入力ファイルが見つかりません -> {INPUT_JSONL}")
        return

    # 2. ルール読み込み
    noise_patterns = load_rules()
    if not noise_patterns:
        print("⚠️ 注意: 除外パターンが登録されていません。")
        return

    print("末尾（接尾辞）フィルタリングを開始します...")
    print(f"・入力元: {INPUT_JSONL}")
    print(f"・除外パターン数: {len(noise_patterns)}件")

    # 3. 正規表現のコンパイル (高速化のため)
    pattern_regex = re.compile("|".join(map(re.escape, noise_patterns)))

    keep_list = []
    discard_list = []
    total_count = 0

    # 4. フィルタリング実行
    with open(INPUT_JSONL, 'r', encoding='utf-8') as f:
        for line in f:
            try:
                row = json.loads(line)
                total_count += 1
                
                # タイトルを取得 (rdfs:label 優先, なければ schema:name)
                label = row.get('rdfs:label')
                name = row.get('schema:name')
                title = str(label) if label else (str(name) if name else "")
                
                if not title:
                    # タイトルがないデータは判定できないため残す
                    keep_list.append(row)
                    continue

                # --- 判定ロジック ---
                match = pattern_regex.search(title)
                
                if match:
                    # NGワードがタイトルに含まれている -> 除外
                    row['exclusion_reason'] = f"Suffix NG: {match.group()}"
                    discard_list.append(row)
                else:
                    # 含まれていない -> 採用
                    keep_list.append(row)

            except json.JSONDecodeError:
                continue

    # 5. 結果の保存 (Keep -> JSONL)
    if keep_list:
        with open(OUTPUT_FINAL_JSONL, 'w', encoding='utf-8') as f:
            for item in keep_list:
                f.write(json.dumps(item, ensure_ascii=False) + '\n')
        print(f"\n✅ [完了] 最終データセット作成成功！")
        print(f"   入力件数: {total_count}件")
        print(f"   採用件数: {len(keep_list)}件 -> {OUTPUT_FINAL_JSONL}")
    else:
        print("\n⚠️ 警告: データが1件も残りませんでした。フィルタ条件を見直してください。")

    # 6. 除外データの保存 (Discard -> CSV)
    if discard_list:
        df_discard = pd.DataFrame(discard_list)
        
        # 見やすいように列を並べ替え
        cols = ['exclusion_reason', 'rdfs:label', 'schema:name']
        valid_cols = [c for c in cols if c in df_discard.columns]
        other_cols = [c for c in df_discard.columns if c not in valid_cols]
        
        # CSV出力
        df_discard[valid_cols + other_cols].to_csv(
            OUTPUT_DISCARDED_CSV, 
            index=False, 
            encoding='utf-8-sig',
            quoting=csv.QUOTE_ALL
        )
        print(f"🗑️ [除外] 除外されたデータ: {len(discard_list)}件 -> {OUTPUT_DISCARDED_CSV}")

if __name__ == "__main__":
    main()
