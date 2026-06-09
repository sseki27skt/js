import json
import random
import os

# =================設定=================
INPUT_FILE = "fragments/llm_judgments.jsonl"      # AIの判定結果（母集団）
OUTPUT_FILE = "fragments/sample_for_human_check.jsonl" # 人間がチェックする用
SAMPLE_SIZE = 300                                 # チェックする件数（300件あれば十分信頼できます）
# ======================================

def main():
    if not os.path.exists(INPUT_FILE):
        print(f"ファイルが見つかりません: {INPUT_FILE}")
        return

    # 全データを読み込む
    all_data = []
    with open(INPUT_FILE, 'r', encoding='utf-8') as f:
        for line in f:
            try:
                all_data.append(json.loads(line))
            except: continue
    
    total = len(all_data)
    print(f"母集団: {total}件")

    # ランダムに抽出
    if total < SAMPLE_SIZE:
        print("データ件数がサンプルサイズより少ないため、全件を出力します。")
        sampled_data = all_data
    else:
        sampled_data = random.sample(all_data, SAMPLE_SIZE)
        print(f"ランダムに {SAMPLE_SIZE} 件を抽出しました。")

    # ファイルに保存
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        for d in sampled_data:
            f.write(json.dumps(d, ensure_ascii=False) + "\n")

    print(f"保存完了: {OUTPUT_FILE}")
    print("次に human_verifier.py の INPUT_FILE をこのファイルに書き換えて実行してください。")

if __name__ == "__main__":
    main()