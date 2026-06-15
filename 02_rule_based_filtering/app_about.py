
import streamlit as st
import pandas as pd
import os
import json
import urllib.parse
import time

# ==========================================
# 0. 基本設定
# ==========================================
st.set_page_config(layout="wide", page_title="Aboutキーワード仕分け")
DEFAULT_FILE = "./data/about_keywords_ranking.csv"
RULES_FILE = "./02_rule_based_filtering/about_rules.json"

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

def toggle_selection(word, key):
    sel_set = st.session_state["selected_words"]
    if key in st.session_state:
        is_checked = st.session_state[key]
        if is_checked:
            sel_set.add(word)
        else:
            if word in sel_set:
                sel_set.remove(word)

def make_google_link(word):
    if str(word).startswith("http"):
        return f"[[🔗]]({word})"
    query = urllib.parse.quote(f"{word} とは")
    url = f"https://www.google.com/search?q={query}"
    return f"[[🔍]]({url})"

def load_rules():
    """rules.json からブラックリスト・ホワイトリストを読み込む"""
    rules = {"NOISE_PATTERNS": [], "STRONG_KEYWORDS": []}
    if os.path.exists(RULES_FILE):
        try:
            with open(RULES_FILE, 'r', encoding='utf-8') as f:
                rules = json.load(f)
        except Exception as e:
            st.error(f"rules.jsonの読み込みエラー: {e}")
    else:
        st.error(f"rules.jsonが存在しません: {RULES_FILE}")
    return rules

def save_rules_all(noise_set, strong_set):
    """両方のリストをまとめて rules.json に保存する"""
    rules = {
        "NOISE_PATTERNS": sorted(list(noise_set)),
        "STRONG_KEYWORDS": sorted(list(strong_set))
    }
    try:
        with open(RULES_FILE, 'w', encoding='utf-8') as f:
            json.dump(rules, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        st.error(f"保存エラー: {e}")
        return False

# ==========================================
# 2. メインアプリ
# ==========================================
st.title("🏷️ Schema:About 仕分けツール")
st.markdown("`schema:about` の分析結果から、**採用したいキーワード** または **除外したいキーワード** を選択してください。")

# --- ロード ---
# --- セッション初期値の設定 ---
if "about_df" not in st.session_state:
    st.session_state["about_df"] = None

if "view_version" not in st.session_state:
    st.session_state["view_version"] = 0

if "list_type" not in st.session_state:
    st.session_state["list_type"] = "ブラックリスト (除外)"

if "edited_noise" not in st.session_state or "edited_strong" not in st.session_state:
    rules_data = load_rules()
    st.session_state["edited_noise"] = set(rules_data.get("NOISE_PATTERNS", []))
    st.session_state["edited_strong"] = set(rules_data.get("STRONG_KEYWORDS", []))

if "selected_words" not in st.session_state:
    st.session_state["selected_words"] = (
        st.session_state["edited_noise"] 
        if st.session_state["list_type"] == "ブラックリスト (除外)" 
        else st.session_state["edited_strong"]
    )

with st.sidebar:
    st.header("設定")
    
    # 編集対象リストの選択
    prev_type = st.session_state["list_type"]
    options = ["ホワイトリスト (残す)", "ブラックリスト (除外)"]
    default_idx = options.index(prev_type) if prev_type in options else 1
    output_type = st.radio("編集対象のリスト", options, index=default_idx, horizontal=False)
    st.session_state["list_type"] = output_type
    
    # 種類が切り替わったら、その種類のリストの参照を代入する
    if prev_type != output_type:
        st.session_state["selected_words"] = (
            st.session_state["edited_strong"] 
            if output_type == "ホワイトリスト (残す)" 
            else st.session_state["edited_noise"]
        )
        st.rerun()

    st.divider()
    st.subheader("表示設定")
    
    # すでに分類済みの語を非表示にするトグル
    hide_classified = st.checkbox(
        "分類済みの語を非表示", 
        value=True, 
        help="about_rules.jsonの既知リスト（ブラック/ホワイト）および、現在選択中の語を画面から隠します"
    )
    
    # 表示件数の上限設定
    max_items = st.number_input("表示件数の上限", min_value=100, max_value=10000, value=1000, step=100, help="動作が重い場合は下げてください")
    
    if st.button("データ読み込み / リセット", use_container_width=True):
        if os.path.exists(DEFAULT_FILE):
            st.session_state["about_df"] = load_csv(DEFAULT_FILE)
            # rules.json から最新の状態を再ロードしてセッションを更新
            rules_data = load_rules()
            st.session_state["edited_noise"] = set(rules_data.get("NOISE_PATTERNS", []))
            st.session_state["edited_strong"] = set(rules_data.get("STRONG_KEYWORDS", []))
            st.session_state["selected_words"] = (
                st.session_state["edited_noise"] 
                if st.session_state["list_type"] == "ブラックリスト (除外)" 
                else st.session_state["edited_strong"]
            )
            st.session_state["view_version"] += 1
            st.rerun()
        else:
            st.error(f"ファイルがありません: {DEFAULT_FILE}")

    st.divider()
    st.subheader(f"選択中: {len(st.session_state['selected_words'])}件")
    
    if st.button("💾 rules.json に保存する", type="primary", use_container_width=True):
        success = save_rules_all(st.session_state["edited_noise"], st.session_state["edited_strong"])
        if success:
            st.success("🎉 保存しました！")
            time.sleep(1)
            st.rerun()
    
    if st.button("全ての選択を解除", key="clear_all_selection", type="secondary", use_container_width=True):
        st.session_state["selected_words"].clear()
        st.session_state["view_version"] += 1 
        st.rerun()

# --- メイン画面 ---
if st.session_state["about_df"] is not None:
    df_all = st.session_state["about_df"]
    
    if "Word" not in df_all.columns:
        st.error("エラー: CSV内にキーワード列が見つかりませんでした。")
        st.stop()

    current_selection = st.session_state["selected_words"]
    
    # 大タブ分け
    tab_main_select, tab_main_output = st.tabs(["🔍 キーワード仕分け", "📄 出力・プレビュー"])
    
    with tab_main_select:
        # --- フィルタリング機能 ---
        col_search, col_dummy = st.columns([1, 2])
        with col_search:
            search_query = st.text_input("キーワード検索 (絞り込み)", placeholder="例: 歴史 -音楽 (スペース区切りで複数指定・マイナスで除外)...")

        df_display = df_all

        # すでに分類済みのキーワードまたは現在選択中のキーワードを隠す
        if hide_classified:
            classified_set = st.session_state["edited_noise"] | st.session_state["edited_strong"] | current_selection
            df_display = df_display[~df_display["Word"].isin(classified_set)]

        if search_query:
            import re
            # 全角スペースを半角スペースに統一して分割
            parts = [p.strip() for p in re.split(r'\s+', search_query.replace('　', ' ')) if p.strip()]
            
            include_words = []
            exclude_words = []
            
            for part in parts:
                if (part.startswith('-') or part.startswith('－')) and len(part) > 1:
                    exclude_words.append(part[1:].lower())
                else:
                    include_words.append(part.lower())
            
            # フィルタリング
            word_series = df_display["Word"].astype(str).str.lower()
            mask = pd.Series(True, index=df_display.index)
            
            for inc in include_words:
                mask = mask & word_series.str.contains(inc, na=False, regex=False)
                
            for exc in exclude_words:
                mask = mask & ~word_series.str.contains(exc, na=False, regex=False)
                
            df_display = df_display[mask]

        # --- サブタブ分け (URI / すべて) ---
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
                    
                    unique_key = f"chk_{tab_id}_{word}_v{view_ver}"
                    
                    col.checkbox(
                        label,
                        value=is_checked,
                        key=unique_key, 
                        on_change=toggle_selection,
                        args=(word, unique_key)
                    )

    with tab_main_output:
        st.subheader("現在の選択リストとコードプレビュー")
        
        final_list = sorted(list(current_selection))
        
        if final_list:
            json_str = json.dumps(final_list, ensure_ascii=False).replace('", "', '",\n    "')
            
            if st.session_state["list_type"] == "ホワイトリスト (残す)":
                var_name = "STRONG_KEYWORDS" 
                st.success("✅ 以下のリストを「残す条件」として使用します（rules.json内：STRONG_KEYWORDS）")
            else:
                var_name = "NOISE_PATTERNS"
                st.error("⛔ 以下のリストを「除外する条件」として使用します（rules.json内：NOISE_PATTERNS）")
                
            st.code(f"{var_name} = {json_str}", language="python")
        else:
            st.info("まだ何も選択されていません")

else:
    st.info("サイドバーのボタンを押してデータを読み込んでください")