# -*- coding: utf-8 -*-
import pandas as pd
import json
import re
import os
import csv

# =================設定=================
# 入力: schema:about でのフィルタリングを通過したファイル
# INPUT_JSONL = "./fragments/classical_scores_about_filtered.jsonl"
INPUT_JSONL = "./fragments/classical_scores_fu_filtered.jsonl"

# 出力: 完成した最終データ
OUTPUT_FINAL_JSONL = "./fragments/classical_scores_fu_filtered2.jsonl"

# 確認用: 除外されたデータのリスト
OUTPUT_DISCARDED_CSV = "./data/discarded_suffix_filtered2.csv"

# ▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼
# ここにアプリで生成された NOISE_PATTERNS を貼り付けてください
# ▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼

NOISE_PATTERNS = ["世編年略譜","中茘枝通譜","人参譜","介譜","代大仏師譜","仮面譜","俳譜","前国画家略譜","勝譜","包譜","南山小譜","博物館介譜","印籠譜","参譜","古今紅葉譜","和歌師資相伝血脉譜","善御譜","営譜","器譜","国譜","園梅譜","埜譜","墨竹譜","字譜","家押譜","封筒譜","小譜","屋譜","嶋譜","巌譜","帝王譜","康濟譜","徳譜","戦前後略譜","扇興譜","押譜","支譜","文獣譜","文解字韻譜","文觧字韻譜","新渡大錢譜","旗譜","日本介譜","日本諸州薬譜","日譜","時宗要略譜","書畫人名譜","朝顔譜","木譜","松島勝譜","柳営譜","桂花園墨譜","桜譜","梅園介譜","梅花喜神譜","梅譜","榧園泉貨譜","橘譜","氏譜","波臣小譜","活語断続譜","濟譜","点俳譜","煙草譜","獣譜","王譜","生譜","畧譜","百花詩箋譜","皇略譜","硯譜","碁譜","筐小袖累譜","筒譜","籠譜","紫巌譜","紺屋譜","脈道統之譜","至桜町院皇子女略譜","興譜","艶譜","芳烈公略譜","苑譜","草略譜","草譜","荒埜譜","華族類別譜","葉譜","蓮譜","藩譜","蟲譜","観微旨掌中譜","貝譜","賢押譜","金譜","銘譜","錢譜","韻譜","顔譜"]

# ▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲

def main():
    # 1. ファイルチェック
    if not os.path.exists(INPUT_JSONL):
        print(f"エラー: 入力ファイルが見つかりません -> {INPUT_JSONL}")
        return

    # 2. リストチェック
    if not NOISE_PATTERNS:
        print("⚠️ 注意: NOISE_PATTERNS が空です。")
        print("アプリからコードをコピーして、スクリプト内のリストに貼り付けてください。")
        return

    print("最終フィルタリングを開始します...")
    print(f"・除外キーワード数: {len(NOISE_PATTERNS)}件")

    # 3. 正規表現のコンパイル (高速化のため)
    # リスト内の単語のいずれかに一致するパターンを作成
    # re.escapeで特殊文字をエスケープし、'|'（OR）で結合
    pattern_regex = re.compile("|".join(map(re.escape, NOISE_PATTERNS)))

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
                    # タイトルがないデータは判定できないため、念のため残すか捨てるか
                    # ここでは安全のため残しますが、必要に応じて変更してください
                    keep_list.append(row)
                    continue

                # --- 判定ロジック ---
                match = pattern_regex.search(title)
                
                if match:
                    # NGワードがタイトルに含まれている -> 除外 (Discard)
                    row['exclusion_reason'] = f"Suffix NG: {match.group()}"
                    discard_list.append(row)
                else:
                    # 含まれていない -> 採用 (Keep)
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
        print("   ※ 念のためCSVを開き、必要な楽譜が巻き込まれていないか確認することをお勧めします。")

if __name__ == "__main__":
    main()