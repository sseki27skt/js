import streamlit as st
import pandas as pd
import os
import json
import urllib.parse

# ==========================================
# 0. 基本設定
# ==========================================
st.set_page_config(layout="wide", page_title="Aboutキーワード仕分け")
DEFAULT_FILE = "./data/about_keywords_ranking_fixed.csv"

# ==========================================
# 1. データ処理関数
# ==========================================
def load_csv(filepath):
    """schema:about のランキングCSVを読み込む"""
    if not os.path.exists(filepath):
        return None
    
    df = pd.read_csv(filepath)
    df.columns = df.columns.str.strip()
    
    if "Keyword" in df.columns:
        df = df.rename(columns={"Keyword": "Word"})
        
    if "Word" not in df.columns and len(df.columns) >= 2:
        target_col = df.columns[1]
        df = df.rename(columns={target_col: "Word"})
        st.toast(f"列 '{target_col}' を 'Word' として読み込みました。", icon="ℹ️")

    return df

def get_selection():
    if "selected_words" not in st.session_state:
        st.session_state["selected_words"] = set()
    return st.session_state["selected_words"]

def toggle_selection(word):
    sel_set = st.session_state["selected_words"]
    if word in sel_set:
        sel_set.remove(word)
    else:
        sel_set.add(word)

def make_google_link(word):
    if str(word).startswith("http"):
        return f"[[🔗]]({word})"
    query = urllib.parse.quote(f"{word} とは")
    url = f"https://www.google.com/search?q={query}"
    return f"[[🔍]]({url})"

# ==========================================
# 2. メインアプリ
# ==========================================
st.title("🏷️ Schema:About 仕分けツール")
st.markdown("`schema:about` の分析結果から、**採用したいキーワード** または **除外したいキーワード** を選択してください。")

# --- ロード ---
if "about_df" not in st.session_state:
    st.session_state["about_df"] = None
if "selected_words" not in st.session_state:
    st.session_state["selected_words"] = set()

if "view_version" not in st.session_state:
    st.session_state["view_version"] = 0

with st.sidebar:
    st.header("設定")
    
    # 【追加】表示件数の上限設定
    max_items = st.number_input("表示件数の上限", min_value=100, max_value=10000, value=1000, step=100, help="動作が重い場合は下げてください")
    
    if st.button("データ読み込み / リセット"):
        if os.path.exists(DEFAULT_FILE):
            st.session_state["about_df"] = load_csv(DEFAULT_FILE)
            st.session_state["selected_words"] = set()
            st.session_state["view_version"] = 0
            st.rerun()
        else:
            st.error(f"ファイルがありません: {DEFAULT_FILE}")

    st.divider()
    st.subheader(f"選択中: {len(st.session_state['selected_words'])}件")
    
    if st.button("全ての選択を解除", type="primary"):
        st.session_state["selected_words"] = set()
        st.session_state["view_version"] += 1 
        st.rerun()

# --- メイン画面 ---
if st.session_state["about_df"] is not None:
    
    df_all = st.session_state["about_df"]
    
    if "Word" not in df_all.columns:
        st.error("エラー: CSV内にキーワード列が見つかりませんでした。")
        st.stop()

    current_selection = st.session_state["selected_words"]
    
    # --- フィルタリング機能 ---
    col_search, col_dummy = st.columns([1, 2])
    with col_search:
        search_query = st.text_input("キーワード検索 (絞り込み)", placeholder="例: ndc, 760...")

    if search_query:
        df_display = df_all[df_all["Word"].astype(str).str.contains(search_query, case=False, na=False, regex=False)]
    else:
        df_display = df_all

    # --- タブ分け ---
    mask_uri = df_display["Word"].astype(str).str.startswith("http")
    df_uri = df_display[mask_uri]
    
    tab_labels = [f"URI ({len(df_uri)})", "すべて"]
    tab_ids = ["tab_uri", "tab_all"]
    target_dfs = [df_uri, df_display]
    
    tabs = st.tabs(tab_labels)
    
    view_ver = st.session_state["view_version"]

    for tab_id, tab, df_target in zip(tab_ids, tabs, target_dfs):
        with tab:
            if df_target.empty:
                st.info("該当するデータがありません")
                continue
            
            # --- 全選択・全解除ボタンエリア ---
            col_act1, col_act2, col_act_dummy = st.columns([1, 1, 6])
            
            # 【変更】設定したmax_itemsを使用
            limit = max_items
            is_limited = False
            
            if len(df_target) > limit:
                is_limited = True
                df_target_view = df_target.head(limit)
                visible_words_view = df_target_view["Word"].tolist()
            else:
                df_target_view = df_target
                visible_words_view = df_target["Word"].tolist()

            with col_act1:
                if st.button("このタブを全選択", key=f"sel_all_{tab_id}"):
                    st.session_state["selected_words"].update(visible_words_view)
                    st.session_state["view_version"] += 1 
                    st.rerun()

            with col_act2:
                if st.button("このタブを全解除", key=f"sel_none_{tab_id}"):
                    st.session_state["selected_words"].difference_update(visible_words_view)
                    st.session_state["view_version"] += 1 
                    st.rerun()

            if is_limited:
                st.warning(f"⚠️ データが多いため、上位 {limit} 件のみを表示・操作対象としています。（サイドバーで上限を変更可能）")
            
            st.divider()

            # --- グリッド表示 ---
            cols = st.columns(3)
            
            for idx, (_, row) in enumerate(df_target_view.iterrows()):
                word = row["Word"]
                count = row["Count"]
                
                is_checked = word in current_selection
                
                col = cols[idx % 3]
                link_icon = make_google_link(word)
                
                display_word = str(word)
                if len(display_word) > 30 and display_word.startswith("http"):
                    display_word = "..." + display_word[-25:]
                
                label = f"**{display_word}** ({count}) {link_icon}"
                
                unique_key = f"chk_{tab_id}_{word}_{idx}_v{view_ver}"
                
                col.checkbox(
                    label,
                    value=is_checked,
                    key=unique_key, 
                    on_change=toggle_selection,
                    args=(word,)
                )

    # --- 出力コード生成 ---
    st.divider()
    st.header("出力コード")
    
    output_type = st.radio("リストの種類", ["ホワイトリスト (残す)", "ブラックリスト (除外)"], horizontal=True)
    
    final_list = sorted(list(current_selection))
    
    if final_list:
        json_str = json.dumps(final_list, ensure_ascii=False).replace('", "', '",\n    "')
        
        if output_type == "ホワイトリスト (残す)":
            var_name = "STRONG_KEYWORDS" 
            st.success("✅ 以下のリストを「残す条件」として使用します")
        else:
            var_name = "NOISE_PATTERNS"
            st.error("⛔ 以下のリストを「除外する条件」として使用します")
            
        st.code(f"{var_name} = {json_str}", language="python")
    else:
        st.info("まだ選択されていません")

else:
    st.info("サイドバーのボタンを押してデータを読み込んでください")