import streamlit as st
import pandas as pd
import json
import os
import urllib.parse

# ==========================================
# 0. 基本設定
# ==========================================
st.set_page_config(layout="wide", page_title="NGキーワード仕分け (スマート版)")

# ファイルパス設定
INPUT_CSV = "fragments/ngram/keyword_mining_ranking.csv"
INPUT_SAMPLES = "fragments/ngram/keyword_samples.json"
OUTPUT_NG_LIST = "fragments/ngram/ng_word_list.txt"

# ==========================================
# 1. データ処理関数
# ==========================================
def load_data():
    """CSVとサンプルJSONを読み込む"""
    if not os.path.exists(INPUT_CSV):
        return None, None
    
    df = pd.read_csv(INPUT_CSV)
    
    samples = {}
    if os.path.exists(INPUT_SAMPLES):
        with open(INPUT_SAMPLES, 'r', encoding='utf-8') as f:
            samples = json.load(f)
            
    return df, samples

def load_existing_ng_list():
    """既存のNGリストがあれば読み込む"""
    if os.path.exists(OUTPUT_NG_LIST):
        with open(OUTPUT_NG_LIST, 'r', encoding='utf-8') as f:
            return set([line.strip() for line in f if line.strip()])
    return set()

def save_ng_list(ng_set):
    """NGリストをファイルに保存"""
    unique_words = sorted(list(ng_set))
    os.makedirs(os.path.dirname(OUTPUT_NG_LIST), exist_ok=True)
    with open(OUTPUT_NG_LIST, 'w', encoding='utf-8') as f:
        for word in unique_words:
            f.write(f"{word}\n")
    return len(unique_words)

def toggle_ng(word):
    """チェックボックスの変更をsession_stateに反映"""
    ng_set = st.session_state["ng_selection"]
    if word in ng_set:
        ng_set.remove(word)
    else:
        ng_set.add(word)

def make_google_link(word):
    """Google検索リンクの生成"""
    query = urllib.parse.quote(f"{word} とは")
    url = f"https://www.google.com/search?q={query}"
    return f"[[🔍]]({url})"

# ==========================================
# 2. メインアプリ
# ==========================================
st.title("🎼 NGキーワード仕分け (スマート判定版)")
st.markdown("短い単語でNG指定済みのものは、自動的にグレーアウトされます（重複作業の防止）。")

# --- 初期化 ---
if "ng_selection" not in st.session_state:
    st.session_state["ng_selection"] = load_existing_ng_list()

# データ読み込み
df, samples_map = load_data()

# --- サイドバー ---
with st.sidebar:
    st.header("設定・保存")
    
    if st.button("💾 NGリストを保存", type="primary"):
        count = save_ng_list(st.session_state["ng_selection"])
        st.success(f"保存しました (全{count}件)")
    
    st.divider()
    
    if st.button("データを再読み込み"):
        st.cache_data.clear()
        st.rerun()

    st.subheader("現在のNGリスト")
    current_list = sorted(list(st.session_state["ng_selection"]))
    st.text_area("登録済み (直接編集不可)", value="\n".join(current_list), height=400)
    st.caption(f"合計: {len(current_list)} 件")


# --- メイン画面 ---
if df is not None:
    
    # N-gramごとの設定定義
    configs = [
        {"n": "2", "label": "2文字 (Bi-gram)", "col_w": "Bi-gram", "col_c": "Bi-Count"},
        {"n": "3", "label": "3文字 (Tri-gram)", "col_w": "Tri-gram", "col_c": "Tri-Count"},
        {"n": "4", "label": "4文字 (Tetra-gram)", "col_w": "Tetra-gram", "col_c": "Tetra-Count"},
        {"n": "5", "label": "5文字 (Penta-gram)", "col_w": "Penta-gram", "col_c": "Penta-Count"},
    ]
    
    # 現在のNGリスト（高速検索用）
    current_ng_set = st.session_state["ng_selection"]

    tabs = st.tabs([c["label"] for c in configs])
    
    for conf, tab in zip(configs, tabs):
        with tab:
            sub_df = df[[conf["col_w"], conf["col_c"]]].dropna()
            
            if sub_df.empty:
                st.info("データがありません")
                continue
            
            n_samples = samples_map.get(conf["n"], {})

            # グリッドレイアウト（4列）
            cols = st.columns(4)
            
            # 上位100件を表示
            for idx, row in sub_df.head(100).iterrows():
                word = str(row[conf["col_w"]])
                count = int(row[conf["col_c"]])
                
                # --- ★ここが追加・変更されたロジック ---
                is_checked = word in current_ng_set
                is_disabled = False
                label_prefix = ""
                
                # まだチェックされていない単語について、「親となる短いNGワード」が含まれていないか確認
                if not is_checked:
                    for parent in current_ng_set:
                        # 条件: 親の方が短く、かつ 親が単語の中に含まれている
                        if len(parent) < len(word) and parent in word:
                            is_disabled = True
                            label_prefix = f"⛔({parent}) " # 理由を表示
                            break 
                # ------------------------------------

                # ツールチップ
                example_list = n_samples.get(word, [])
                if example_list:
                    tooltip = f"【{word}】を含むタイトルの例:\n" + "\n".join([f"・{t}" for t in example_list])
                else:
                    tooltip = "サンプルなし"

                search_link = make_google_link(word)
                
                # ラベル生成 (グレーアウト時は理由を表示)
                if is_disabled:
                    label = f"{label_prefix}~~{word}~~ ({count}) {search_link}" # 取り消し線
                else:
                    label = f"**{word}** ({count}) {search_link}"
                
                col = cols[idx % 4]
                
                col.checkbox(
                    label,
                    value=is_checked,
                    key=f"chk_{conf['n']}_{word}_{idx}",
                    disabled=is_disabled, # ★ここで無効化を適用
                    help=tooltip,
                    on_change=toggle_ng,
                    args=(word,)
                )
            
            st.caption("※ ⛔マークは、より短いキーワードですでにNG指定されているため、自動的に除外されるものです。")

else:
    st.error("データファイルが見つかりません。先に `ngram_with_context.py` を実行してください。")