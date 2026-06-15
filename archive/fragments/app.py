import streamlit as st
import pandas as pd
import re
import os
import json
import urllib.parse

# ==========================================
# 0. 基本設定
# ==========================================
st.set_page_config(layout="wide", page_title="キーワード仕分け (Last9対応版)")
DEFAULT_FILE = "./fragments/suffix_analysis_extended.csv"
SAMPLE_FILE = "./fragments/suffix_samples.json"

# ==========================================
# 1. データ処理関数
# ==========================================
def load_and_parse_csv(filepath):
    """CSVを読み込み、タブごとのデータフレーム辞書を作成"""
    if not os.path.exists(filepath):
        return None

    raw_df = pd.read_csv(filepath)
    parsed_data = {}
    
    # 【変更】Last9まで拡張
    target_cols = [f"Last{i}" for i in range(2, 10)]

    for key in target_cols:
        found_col = next((c for c in raw_df.columns if key in c), None)
        if not found_col:
            continue
            
        rows = []
        for val in raw_df[found_col].dropna():
            if not isinstance(val, str) or not val: continue
            match = re.match(r"(.+) \((\d+)\)", val)
            if match:
                rows.append({
                    "Word": match.group(1),
                    "Count": int(match.group(2))
                })
        
        if rows:
            df = pd.DataFrame(rows).sort_values("Count", ascending=False)
            parsed_data[key] = df
        else:
            parsed_data[key] = pd.DataFrame(columns=["Word", "Count"])
            
    return parsed_data

def load_samples(filepath):
    if os.path.exists(filepath):
        with open(filepath, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}

def get_all_ng_words():
    if "ng_selection" not in st.session_state:
        st.session_state["ng_selection"] = set()
    return st.session_state["ng_selection"]

def toggle_ng(word):
    ng_set = st.session_state["ng_selection"]
    if word in ng_set:
        ng_set.remove(word)
    else:
        ng_set.add(word)

def make_google_link(word):
    query = urllib.parse.quote(f"{word} とは")
    url = f"https://www.google.com/search?q={query}"
    return f"[[🔍]]({url})"

# ==========================================
# 2. メインアプリ
# ==========================================
st.title("🎼 NGキーワード仕分け (Last9対応版)")
st.markdown("チェックボックスでNGを選択。Last9までの長い単語に対応しました。")

# --- ロード ---
if "data_store" not in st.session_state:
    st.session_state["data_store"] = {}
if "sample_map" not in st.session_state:
    st.session_state["sample_map"] = {}
if "ng_selection" not in st.session_state:
    st.session_state["ng_selection"] = set()

with st.sidebar:
    st.header("設定")
    if st.button("データ読み込み / リセット"):
        if os.path.exists(DEFAULT_FILE):
            st.session_state["data_store"] = load_and_parse_csv(DEFAULT_FILE)
            st.session_state["sample_map"] = load_samples(SAMPLE_FILE)
            st.session_state["ng_selection"] = set()
            st.rerun()
        else:
            st.error("CSVファイルがありません")

    st.divider()
    st.subheader("現在のNGリスト")
    st.write(sorted(list(st.session_state["ng_selection"])))

# --- メイン画面 ---
if st.session_state["data_store"]:
    
    current_ng_set = st.session_state["ng_selection"]
    sample_map = st.session_state["sample_map"]
    
    # 【変更】タブ生成をループで動的に作成
    tab_labels = [f"Last{i}" for i in range(2, 10)]
    tabs = st.tabs(tab_labels)
    
    for tab, key in zip(tabs, tab_labels):
        with tab:
            df = st.session_state["data_store"].get(key, pd.DataFrame())
            if df.empty:
                st.info("データなし")
                continue

            st.caption(f"{key} の頻出単語 (Top 100)")

            cols = st.columns(4)
            
            for idx, row in df.head(100).iterrows():
                word = row["Word"]
                count = row["Count"]
                
                # グレーアウト判定
                is_disabled = False
                label_prefix = ""
                is_checked = word in current_ng_set
                
                if not is_checked:
                    for parent in current_ng_set:
                        if len(parent) < len(word) and word.endswith(parent):
                            is_disabled = True
                            label_prefix = f"⛔({parent}) "
                            break
                
                # ツールチップ
                example_list = sample_map.get(word, [])
                if example_list:
                    tooltip = "【含まれる資料の例】\n" + "\n".join([f"・{t}" for t in example_list])
                else:
                    tooltip = "サンプルなし"

                # UI表示
                col = cols[idx % 4]
                search_link = make_google_link(word)
                label = f"{label_prefix}**{word}** ({count})  {search_link}"
                
                col.checkbox(
                    label,
                    value=is_checked,
                    key=f"chk_{key}_{word}",
                    disabled=is_disabled,
                    help=tooltip,
                    on_change=toggle_ng,
                    args=(word,)
                )

    # --- 出力 ---
    st.divider()
    st.header("出力コード")
    final_list = sorted(list(current_ng_set))
    if final_list:
        code_text = json.dumps(final_list, ensure_ascii=False).replace('", "', '",\n    "')
        st.code(f"NOISE_PATTERNS = {code_text}", language="python")
    else:
        st.info("選択なし")

else:
    st.info("サイドバーのボタンを押してデータを読み込んでください")