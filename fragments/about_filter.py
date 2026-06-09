import pandas as pd
import json
import re
import os
import csv

# =================設定=================
INPUT_JSONL = "./data/classical_scores_dynamic.jsonl"
OUTPUT_FINAL_JSONL = "./fragments/classical_scores_about_filtered.jsonl"
OUTPUT_DISCARDED_CSV = "./data/discarded_final.csv"

# ▼▼▼ ツールで作成したリストをここに貼り付けてください ▼▼▼

# ⛔ ブラックリスト (除外したいキーワード: 家譜, 年譜, 特定のURIなど)
NOISE_PATTERNS = [
    "https://jpsearch.go.jp/term/keyword/一般図書--語学",
    "https://jpsearch.go.jp/term/keyword/一般資料--芸術--絵画",
    "https://jpsearch.go.jp/term/keyword/仏教_伝記",
    "https://jpsearch.go.jp/term/keyword/仏教_年譜",
    "https://jpsearch.go.jp/term/keyword/仏教_記録",
    "https://jpsearch.go.jp/term/keyword/伝記",
    "https://jpsearch.go.jp/term/keyword/伝記--人名録類",
    "https://jpsearch.go.jp/term/keyword/伝記_地誌",
    "https://jpsearch.go.jp/term/keyword/俳文",
    "https://jpsearch.go.jp/term/keyword/俳諧",
    "https://jpsearch.go.jp/term/keyword/俳諧--書簡集",
    "https://jpsearch.go.jp/term/keyword/入木道新書",
    "https://jpsearch.go.jp/term/keyword/典籍--和漢書",
    "https://jpsearch.go.jp/term/keyword/動物",
    "https://jpsearch.go.jp/term/keyword/動物画",
    "https://jpsearch.go.jp/term/keyword/医学",
    "https://jpsearch.go.jp/term/keyword/医学--本草",
    "https://jpsearch.go.jp/term/keyword/医学--漢方--本草",
    "https://jpsearch.go.jp/term/keyword/医学--漢方--本草--薬性附食治",
    "https://jpsearch.go.jp/term/keyword/医学--漢方--総説",
    "https://jpsearch.go.jp/term/keyword/医学--総記--歴史--伝記--叢伝",
    "https://jpsearch.go.jp/term/keyword/印章",
    "https://jpsearch.go.jp/term/keyword/印譜",
    "https://jpsearch.go.jp/term/keyword/古書類_筆書_--歴史",
    "https://jpsearch.go.jp/term/keyword/和書--総記--叢書",
    "https://jpsearch.go.jp/term/keyword/哲学--仏教--寺院・僧職",
    "https://jpsearch.go.jp/term/keyword/哲学・宗教",
    "https://jpsearch.go.jp/term/keyword/哲学・宗教--仏教",
    "https://jpsearch.go.jp/term/keyword/囲碁",
    "https://jpsearch.go.jp/term/keyword/図案",
    "https://jpsearch.go.jp/term/keyword/国書--兵事・武技--武器",
    "https://jpsearch.go.jp/term/keyword/国書--武学・武術--武具",
    "https://jpsearch.go.jp/term/keyword/国書--武学・武術--近代軍事--陸軍",
    "https://jpsearch.go.jp/term/keyword/国書--武学・武術--馬術",
    "https://jpsearch.go.jp/term/keyword/国書--歴史--日本史--系譜",
    "https://jpsearch.go.jp/term/keyword/国書--歴史・伝記--伝記",
    "https://jpsearch.go.jp/term/keyword/国書--法制・経済--経済",
    "https://jpsearch.go.jp/term/keyword/国書--産業・科学--医学",
    "https://jpsearch.go.jp/term/keyword/国書--総記--叢書",
    "https://jpsearch.go.jp/term/keyword/国書--総記--図書",
    "https://jpsearch.go.jp/term/keyword/国書--美術・諸芸--工芸",
    "https://jpsearch.go.jp/term/keyword/国書--美術・諸芸--花押・印章",
    "https://jpsearch.go.jp/term/keyword/国書--美術・諸芸--遊戯・飲食",
    "https://jpsearch.go.jp/term/keyword/国書--芸術--書画--総記",
    "https://jpsearch.go.jp/term/keyword/国書の部--歴史",
    "https://jpsearch.go.jp/term/keyword/国書の部--歴史--伝記",
    "https://jpsearch.go.jp/term/keyword/国書の部--歴史--伝記・系譜",
    "https://jpsearch.go.jp/term/keyword/国書の部--歴史--雑史",
    "https://jpsearch.go.jp/term/keyword/国書の部--自然科学--薬学",
    "https://jpsearch.go.jp/term/keyword/国書の部--芸術--武道--剣道",
    "https://jpsearch.go.jp/term/keyword/国書之部--芸術--工芸",
    "https://jpsearch.go.jp/term/keyword/国書等和装本--文学--日本文学--詩歌",
    "https://jpsearch.go.jp/term/keyword/国書等和装本--文学--日本文学--詩歌・韻文・詩文",
    "https://jpsearch.go.jp/term/keyword/国漢書--増加分_未分類",
    "https://jpsearch.go.jp/term/keyword/地理--外国地誌--世界誌",
    "https://jpsearch.go.jp/term/keyword/地理--日本地誌--遊覧・遊歴",
    "https://jpsearch.go.jp/term/keyword/地理・地誌--旧仙台領・宮城県地誌--宮城郡_含_仙台_--松島町関係",
    "https://jpsearch.go.jp/term/keyword/地理・地誌--旧仙台領・宮城県地誌--旧仙台領・宮城県関係",
    "https://jpsearch.go.jp/term/keyword/地誌",
    "https://jpsearch.go.jp/term/keyword/外交_記録",
    "https://jpsearch.go.jp/term/keyword/外国語",
    "https://jpsearch.go.jp/term/keyword/大日経教系--宗派",
    "https://jpsearch.go.jp/term/keyword/天満宮文庫蔵書--語学--中国語",
    "https://jpsearch.go.jp/term/keyword/島原藩",
    "https://jpsearch.go.jp/term/keyword/工学_工業--河川工学",
    "https://jpsearch.go.jp/term/keyword/工芸",
    "https://jpsearch.go.jp/term/keyword/工芸図鑑",
    "https://jpsearch.go.jp/term/keyword/庶民教育",
    "https://jpsearch.go.jp/term/keyword/役者評判記",
    "https://jpsearch.go.jp/term/keyword/戦記",
    "https://jpsearch.go.jp/term/keyword/掛軸",
    "https://jpsearch.go.jp/term/keyword/政治・法制・故実--補任・武鑑",
    "https://jpsearch.go.jp/term/keyword/政治・法制付故実--官職--武家",
    "https://jpsearch.go.jp/term/keyword/教育",
    "https://jpsearch.go.jp/term/keyword/文学",
    "https://jpsearch.go.jp/term/keyword/文学--日本文学--詩歌",
    "https://jpsearch.go.jp/term/keyword/文学--日本漢文",
    "https://jpsearch.go.jp/term/keyword/文学--漢文",
    "https://jpsearch.go.jp/term/keyword/文学--漢文--詩文評・作詩作文",
    "https://jpsearch.go.jp/term/keyword/文学・語学--和歌",
    "https://jpsearch.go.jp/term/keyword/文学・語学--小説・戯曲・戯文",
    "https://jpsearch.go.jp/term/keyword/文学・語学--文集・随筆・雑考",
    "https://jpsearch.go.jp/term/keyword/新学--語学",
    "https://jpsearch.go.jp/term/keyword/日本文学",
    "https://jpsearch.go.jp/term/keyword/日記",
    "https://jpsearch.go.jp/term/keyword/書画",
    "https://jpsearch.go.jp/term/keyword/書画_名鑑",
    "https://jpsearch.go.jp/term/keyword/書道",
    "https://jpsearch.go.jp/term/keyword/書道_系譜",
    "https://jpsearch.go.jp/term/keyword/服部家旧蔵一般書--伝記--系譜・家伝",
    "https://jpsearch.go.jp/term/keyword/服部家旧蔵一般書--医学",
    "https://jpsearch.go.jp/term/keyword/服部家旧蔵一般書--文学--漢詩--雑書・雑誌",
    "https://jpsearch.go.jp/term/keyword/服部家旧蔵一般書--歴史--通史・時代史・地方史",
    "https://jpsearch.go.jp/term/keyword/本草",
    "https://jpsearch.go.jp/term/keyword/植物",
    "https://jpsearch.go.jp/term/keyword/植物_和歌",
    "https://jpsearch.go.jp/term/keyword/武具",
    "https://jpsearch.go.jp/term/keyword/武具_系譜",
    "https://jpsearch.go.jp/term/keyword/武学--武具",
    "https://jpsearch.go.jp/term/keyword/武学--総記",
    "https://jpsearch.go.jp/term/keyword/武学・武術--武具",
    "https://jpsearch.go.jp/term/keyword/武学・武術--武具--刀剣",
    "https://jpsearch.go.jp/term/keyword/武学・武術--近代軍事",
    "https://jpsearch.go.jp/term/keyword/武家故実",
    "https://jpsearch.go.jp/term/keyword/武芸--武術",
    "https://jpsearch.go.jp/term/keyword/歴史",
    "https://jpsearch.go.jp/term/keyword/歴史--仙台藩関係--大槻氏関係資料",
    "https://jpsearch.go.jp/term/keyword/歴史--伝記",
    "https://jpsearch.go.jp/term/keyword/歴史--伝記--系譜・紋章・皇室",
    "https://jpsearch.go.jp/term/keyword/歴史--地誌・紀行",
    "https://jpsearch.go.jp/term/keyword/歴史--日本",
    "https://jpsearch.go.jp/term/keyword/歴史--日本史",
    "https://jpsearch.go.jp/term/keyword/歴史--日本史--伝記",
    "https://jpsearch.go.jp/term/keyword/歴史--日本史--伝記・系譜--総伝",
    "https://jpsearch.go.jp/term/keyword/歴史--日本史--史料--総記",
    "https://jpsearch.go.jp/term/keyword/歴史--日本史--時代史",
    "https://jpsearch.go.jp/term/keyword/歴史--日本史--系譜",
    "https://jpsearch.go.jp/term/keyword/歴史--日本史--系譜--家伝",
    "https://jpsearch.go.jp/term/keyword/歴史--日本史--系譜--諸家",
    "https://jpsearch.go.jp/term/keyword/歴史--日本史--記録",
    "https://jpsearch.go.jp/term/keyword/歴史--日本史--雑史--日本史一般",
    "https://jpsearch.go.jp/term/keyword/歴史--日本歴史--叢書",
    "https://jpsearch.go.jp/term/keyword/歴史--日本歴史--系譜",
    "https://jpsearch.go.jp/term/keyword/歴史--系譜",
    "https://jpsearch.go.jp/term/keyword/歴史--記録・文書",
    "https://jpsearch.go.jp/term/keyword/歴史--近世",
    "https://jpsearch.go.jp/term/keyword/歴史・伝記の部--系譜・家史・皇室",
    "https://jpsearch.go.jp/term/keyword/歴史・伝記・地理--伝記",
    "https://jpsearch.go.jp/term/keyword/歴史・地理",
    "https://jpsearch.go.jp/term/keyword/歴史・地理--伝記",
    "https://jpsearch.go.jp/term/keyword/歴史・地理--年譜・系図",
    "https://jpsearch.go.jp/term/keyword/歴史物語",
    "https://jpsearch.go.jp/term/keyword/江戸--言語--音韻",
    "https://jpsearch.go.jp/term/keyword/浄土_系譜",
    "https://jpsearch.go.jp/term/keyword/演劇_絵本",
    "https://jpsearch.go.jp/term/keyword/漢学",
    "https://jpsearch.go.jp/term/keyword/漢学--洋学・本草",
    "https://jpsearch.go.jp/term/keyword/漢文",
    "https://jpsearch.go.jp/term/keyword/漢籍の部--経部--小学類",
    "https://jpsearch.go.jp/term/keyword/漢詩",
    "https://jpsearch.go.jp/term/keyword/漢詩文",
    "https://jpsearch.go.jp/term/keyword/無量寿経教系--宗派",
    "https://jpsearch.go.jp/term/keyword/物語",
    "https://jpsearch.go.jp/term/keyword/理学",
    "https://jpsearch.go.jp/term/keyword/理学--博物",
    "https://jpsearch.go.jp/term/keyword/理学--天文・暦算・測量",
    "https://jpsearch.go.jp/term/keyword/理学・工学・農学",
    "https://jpsearch.go.jp/term/keyword/産業--絵画",
    "https://jpsearch.go.jp/term/keyword/産業--花卉園芸",
    "https://jpsearch.go.jp/term/keyword/産業--農業附救荒",
    "https://jpsearch.go.jp/term/keyword/画帖",
    "https://jpsearch.go.jp/term/keyword/画譜",
    "https://jpsearch.go.jp/term/keyword/石川県関係刊本--歴史--日本史",
    "https://jpsearch.go.jp/term/keyword/社会科学--国防_軍事--陸軍--日本法制史--後期_封建制度_藩政",
    "https://jpsearch.go.jp/term/keyword/社会科学--国防・軍事",
    "https://jpsearch.go.jp/term/keyword/社会科学--学習指導_教科課程--教科書",
    "https://jpsearch.go.jp/term/keyword/社会科学--日本法制史--武家法後期・藩政",
    "https://jpsearch.go.jp/term/keyword/社会科学--経済--貨幣・通貨・為替",
    "https://jpsearch.go.jp/term/keyword/社会科学--軍事--和蘭兵法",
    "https://jpsearch.go.jp/term/keyword/系図",
    "https://jpsearch.go.jp/term/keyword/系譜",
    "https://jpsearch.go.jp/term/keyword/系譜_伝記",
    "https://jpsearch.go.jp/term/keyword/経済--度量衡・貨幣",
    "https://jpsearch.go.jp/term/keyword/経済--度量衡・貨弊",
    "https://jpsearch.go.jp/term/keyword/経済・社会",
    "https://jpsearch.go.jp/term/keyword/絵手本",
    "https://jpsearch.go.jp/term/keyword/絵手本_山水",
    "https://jpsearch.go.jp/term/keyword/絵本",
    "https://jpsearch.go.jp/term/keyword/絵本番附",
    "https://jpsearch.go.jp/term/keyword/絵本番附_操芝居",
    "https://jpsearch.go.jp/term/keyword/絵画",
    "https://jpsearch.go.jp/term/keyword/絵画--画譜類",
    "https://jpsearch.go.jp/term/keyword/総記--双書・全集",
    "https://jpsearch.go.jp/term/keyword/総記--叢書",
    "https://jpsearch.go.jp/term/keyword/総記--叢書_全集",
    "https://jpsearch.go.jp/term/keyword/総記--叢書・全集",
    "https://jpsearch.go.jp/term/keyword/総記--手記・備忘",
    "https://jpsearch.go.jp/term/keyword/総記--歴史",
    "https://jpsearch.go.jp/term/keyword/総記--諸目録",
    "https://jpsearch.go.jp/term/keyword/総記--随叢",
    "https://jpsearch.go.jp/term/keyword/総記--随叢--雑抄",
    "https://jpsearch.go.jp/term/keyword/肉筆画稿帖",
    "https://jpsearch.go.jp/term/keyword/自然科学--医学--基礎医学--解剖学",
    "https://jpsearch.go.jp/term/keyword/自然科学--薬学--本草学",
    "https://jpsearch.go.jp/term/keyword/自然科学--薬学・本草学",
    "https://jpsearch.go.jp/term/keyword/花押",
    "https://jpsearch.go.jp/term/keyword/花道",
    "https://jpsearch.go.jp/term/keyword/花鳥画",
    "https://jpsearch.go.jp/term/keyword/芸術--印刷_製版",
    "https://jpsearch.go.jp/term/keyword/芸術--工芸",
    "https://jpsearch.go.jp/term/keyword/芸術--書画",
    "https://jpsearch.go.jp/term/keyword/芸術--書画--絵画",
    "https://jpsearch.go.jp/term/keyword/芸術--書画--総記",
    "https://jpsearch.go.jp/term/keyword/芸術--書画・考古・印譜",
    "https://jpsearch.go.jp/term/keyword/芸術--書道",
    "https://jpsearch.go.jp/term/keyword/芸術--書道--文房具",
    "https://jpsearch.go.jp/term/keyword/芸術--書道--書法・筆法",
    "https://jpsearch.go.jp/term/keyword/芸術--書道--落款・印譜",
    "https://jpsearch.go.jp/term/keyword/芸術--書道・絵画",
    "https://jpsearch.go.jp/term/keyword/芸術--絵画--日本画",
    "https://jpsearch.go.jp/term/keyword/芸術--茶道",
    "https://jpsearch.go.jp/term/keyword/芸術--茶道・香道",
    "https://jpsearch.go.jp/term/keyword/芸術--金工芸",
    "https://jpsearch.go.jp/term/keyword/芸術--金工芸・武具",
    "https://jpsearch.go.jp/term/keyword/芸術--香道",
    "https://jpsearch.go.jp/term/keyword/芸術・美術--工芸--金工芸・刀剣・甲冑",
    "https://jpsearch.go.jp/term/keyword/芸術・美術--武道",
    "https://jpsearch.go.jp/term/keyword/芸術・美術--花道",
    "https://jpsearch.go.jp/term/keyword/芸術・趣味--香道・その他",
    "https://jpsearch.go.jp/term/keyword/茶道",
    "https://jpsearch.go.jp/term/keyword/茶道_建築",
    "https://jpsearch.go.jp/term/keyword/茶道_黄檗",
    "https://jpsearch.go.jp/term/keyword/薬物",
    "https://jpsearch.go.jp/term/keyword/藩主--系譜",
    "https://jpsearch.go.jp/term/keyword/複製",
    "https://jpsearch.go.jp/term/keyword/西高辻家蔵書--芸術--書画",
    "https://jpsearch.go.jp/term/keyword/言語--語法",
    "https://jpsearch.go.jp/term/keyword/記録",
    "https://jpsearch.go.jp/term/keyword/詩歌",
    "https://jpsearch.go.jp/term/keyword/語学",
    "https://jpsearch.go.jp/term/keyword/語学--日本語",
    "https://jpsearch.go.jp/term/keyword/諸芸--書道",
    "https://jpsearch.go.jp/term/keyword/諸芸--茶道",
    "https://jpsearch.go.jp/term/keyword/諸芸--遊戯--囲碁・将棊",
    "https://jpsearch.go.jp/term/keyword/諸芸--遊技--囲碁将棊",
    "https://jpsearch.go.jp/term/keyword/諸芸--遊技・遊戯",
    "https://jpsearch.go.jp/term/keyword/貨幣",
    "https://jpsearch.go.jp/term/keyword/軍記物語",
    "https://jpsearch.go.jp/term/keyword/農書",
    "https://jpsearch.go.jp/term/keyword/近世刊本--歴史--伝記--系譜",
    "https://jpsearch.go.jp/term/keyword/近世刊本--芸術--絵画--書道_書画",
    "https://jpsearch.go.jp/term/keyword/遊女絵本",
    "https://jpsearch.go.jp/term/keyword/金工",
    "https://jpsearch.go.jp/term/keyword/音楽_系譜",
    "https://jpsearch.go.jp/term/keyword/風俗",
    "https://jpsearch.go.jp/term/keyword/風俗絵本",
    "https://jpsearch.go.jp/term/keyword/香道",
    "https://jpsearch.go.jp/term/keyword/馬具",
    "https://jpsearch.go.jp/term/keyword/馬術",
    "https://jpsearch.go.jp/term/keyword/魚介",
    "https://jpsearch.go.jp/term/keyword/魚介画"
]

# ✅ ホワイトリスト (絶対に守りたいキーワード: 楽譜, 笛譜, 音楽URIなど)
# ※ ここに含まれる単語があれば、ブラックリストに該当しても「救済」されます
STRONG_KEYWORDS = [
    # 例: "笛譜", "琴譜"
]

# ======================================

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
        with open(OUTPUT_FINAL_JSONL, 'w', encoding='utf-8') as f:
            for item in keep_list:
                f.write(json.dumps(item, ensure_ascii=False) + '\n')
        print(f"\n✅ [完成] 最終データ: {len(keep_list)}件 -> {OUTPUT_FINAL_JSONL}")
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

if __name__ == "__main__":
    main()