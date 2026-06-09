import json
import os
from collections import Counter

# =================設定=================
# 1. 入力データ（前回の処理結果）
INPUT_JSONL = "fragments/classical_scores_fu_filtered2.jsonl"

# 2. NGワードリスト（作成したテキストファイル）
NG_LIST_FILE = "fragments/ngram/ng_word_list_final.txt"

# 3. 出力ファイル（クリーンになったデータ）
OUTPUT_CLEAN = "fragments/classical_scores_fu_filtered3.jsonl"

# 4. 除外データ保存用（確認のため）
OUTPUT_REMOVED = "fragments/removed_by_ngram.jsonl"
# ======================================

def main():
    # 1. NGリストの読み込み
    if not os.path.exists(NG_LIST_FILE):
        print(f"エラー: NGリストが見つかりません ({NG_LIST_FILE})")
        return

    with open(NG_LIST_FILE, 'r', encoding='utf-8') as f:
        # 空行を除去してリスト化
        ng_words = [line.strip() for line in f if line.strip()]

    print(f"NGワード {len(ng_words)} 件を読み込みました。フィルタリングを開始します...")

    # カウンター
    total_count = 0
    keep_count = 0
    remove_count = 0
    ng_hit_stats = Counter() # どのNGワードで消えたかをカウント

    # 2. フィルタリング処理
    with open(INPUT_JSONL, 'r', encoding='utf-8') as fin, \
         open(OUTPUT_CLEAN, 'w', encoding='utf-8') as f_clean, \
         open(OUTPUT_REMOVED, 'w', encoding='utf-8') as f_removed:

        for line in fin:
            try:
                data = json.loads(line)
                total_count += 1

                # タイトル取得
                label = data.get('rdfs:label')
                name = data.get('schema:name')
                title = str(label) if label else (str(name) if name else "")

                # 判定ロジック
                hit_ng_word = None
                for ng in ng_words:
                    if ng in title:
                        hit_ng_word = ng
                        break # 1つでもヒットすればNG

                if hit_ng_word:
                    # NGの場合
                    remove_count += 1
                    ng_hit_stats[hit_ng_word] += 1
                    
                    # どのワードで消えたかをデータに追加して保存（デバッグ用）
                    data['_removed_reason'] = hit_ng_word
                    f_removed.write(json.dumps(data, ensure_ascii=False) + "\n")
                else:
                    # OKの場合
                    keep_count += 1
                    f_clean.write(line)

            except json.JSONDecodeError:
                continue

    # 3. 結果表示
    print("-" * 50)
    print(f"処理完了")
    print(f"入力件数: {total_count}")
    print(f"残ったデータ: {keep_count} (保存先: {OUTPUT_CLEAN})")
    print(f"削除したデータ: {remove_count} (保存先: {OUTPUT_REMOVED})")
    print("-" * 50)

    if remove_count > 0:
        print("\n[削除原因となったNGワード Top 20]")
        for word, count in ng_hit_stats.most_common(20):
            print(f"{word}: {count}件")
        
        print("\n※ 意図せず大量に削除されている単語がないか確認してください。")

if __name__ == "__main__":
    main()