import json
import os
from collections import Counter

# =================設定=================
INPUT_JSONL = "fragments/classical_scores_fu_filtered3.jsonl" # 元データ
LIST_NG = "fragments/ngram/ng_word_list.txt"
LIST_OK = "fragments/ngram/ok_word_list.txt"

# 出力先
OUT_CONFIRMED = "fragments/final_confirmed_scores.jsonl" # 確定(OK)
OUT_REMOVED = "fragments/final_removed_noise.jsonl"      # 削除(NG)
OUT_GRAY = "fragments/target_for_llm.jsonl"              # 未定(LLMへ)
# ======================================

def load_list(path):
    if os.path.exists(path):
        with open(path, 'r', encoding='utf-8') as f:
            return [line.strip() for line in f if line.strip()]
    return []

def main():
    ng_words = load_list(LIST_NG)
    ok_words = load_list(LIST_OK)
    
    print(f"NGワード: {len(ng_words)}件 / OKワード: {len(ok_words)}件 を読み込みました。")
    
    counts = {"ok": 0, "ng": 0, "gray": 0}
    reasons_ok = Counter()
    reasons_ng = Counter()

    with open(INPUT_JSONL, 'r', encoding='utf-8') as fin, \
         open(OUT_CONFIRMED, 'w', encoding='utf-8') as f_ok, \
         open(OUT_REMOVED, 'w', encoding='utf-8') as f_ng, \
         open(OUT_GRAY, 'w', encoding='utf-8') as f_gray:

        for line in fin:
            try:
                data = json.loads(line)
                
                label = data.get('rdfs:label')
                name = data.get('schema:name')
                title = str(label) if label else (str(name) if name else "")
                
                # 判定ロジック
                # 1. まずNG判定（NGが含まれていたら即削除）
                # ※ OKワードが入っていても、NGワード（例：「目録」）が入っていたら削除する安全策
                hit_ng = next((w for w in ng_words if w in title), None)
                if hit_ng:
                    counts["ng"] += 1
                    reasons_ng[hit_ng] += 1
                    data["_filter_reason"] = f"NG: {hit_ng}"
                    f_ng.write(json.dumps(data, ensure_ascii=False) + "\n")
                    continue

                # 2. 次にOK判定
                hit_ok = next((w for w in ok_words if w in title), None)
                if hit_ok:
                    counts["ok"] += 1
                    reasons_ok[hit_ok] += 1
                    data["_filter_reason"] = f"OK: {hit_ok}"
                    # ここでLLM判定スキップのフラグを立てておく
                    data["is_score"] = True 
                    f_ok.write(json.dumps(data, ensure_ascii=False) + "\n")
                    continue

                # 3. 残りはグレーゾーン（LLM行き）
                counts["gray"] += 1
                f_gray.write(line)

            except json.JSONDecodeError:
                continue

    print("-" * 50)
    print(f"処理結果:")
    print(f"✅ 確定 (OK) : {counts['ok']} 件 -> {OUT_CONFIRMED}")
    print(f"⛔ 削除 (NG) : {counts['ng']} 件 -> {OUT_REMOVED}")
    print(f"🤔 未定 (Gray): {counts['gray']} 件 -> {OUT_GRAY}")
    print("-" * 50)
    
    if counts['gray'] > 0:
        print("【次のステップ】")
        print(f"「{OUT_GRAY}」に対してのみ、LLMスクリプトを実行してください。")
        print("コストと時間を大幅に削減できます。")

if __name__ == "__main__":
    main()