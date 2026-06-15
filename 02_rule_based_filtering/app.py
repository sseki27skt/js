import streamlit as st
import pandas as pd
import re
import os
import json
import urllib.parse

# ==========================================
# 0. 基本設定
# ==========================================
st.set_page_config(layout="wide", page_title="キーワード仕分け (Last9・全量対応版)")
DEFAULT_FILE = "./data/suffix_analysis_extended.csv"
SAMPLE_FILE = "./data/suffix_samples.json"
RULES_FILE = "./02_rule_based_filtering/suffix_rules.json"

def load_rules():
    """suffix_rules.json からNGパターンリストを読み込む"""
    rules = []
    if os.path.exists(RULES_FILE):
        try:
            with open(RULES_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                rules = data.get("NOISE_PATTERNS", [])
        except:
            pass
    return rules

def save_rules(ng_selection):
    """仕分けたNGパターンを suffix_rules.json に保存する"""
    rules = {
        "NOISE_PATTERNS": sorted(list(ng_selection))
    }
    try:
        with open(RULES_FILE, 'w', encoding='utf-8') as f:
            json.dump(rules, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        st.error(f"保存エラー: {e}")
        return False

# ==========================================
# 1. データ処理関数
# ==========================================
def load_and_parse_csv(filepath):
    """CSVを読み込み、タブごとのデータフレーム辞書を作成"""
    if not os.path.exists(filepath):
        return None

    raw_df = pd.read_csv(filepath)
    parsed_data = {}
    
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

def toggle_ng(word, key):
    ng_set = st.session_state["ng_selection"]
    if key in st.session_state:
        is_checked = st.session_state[key]
        if is_checked:
            ng_set.add(word)
        else:
            if word in ng_set:
                ng_set.remove(word)

def make_google_link(word):
    query = urllib.parse.quote(f"{word} とは")
    url = f"https://www.google.com/search?q={query}"
    return f"[[🔍]]({url})"

# ==========================================
# 2. メインアプリ
# ==========================================
st.title("🎼 NGキーワード仕分け (Last9・全量対応版)")
st.markdown("すべての候補データを表示できます。サイドバーで表示件数を調整してください。")

# --- ロード ---
if "data_store" not in st.session_state:
    st.session_state["data_store"] = {}
if "sample_map" not in st.session_state:
    st.session_state["sample_map"] = {}
if "ng_selection" not in st.session_state:
    st.session_state["ng_selection"] = set(load_rules())

if "view_version" not in st.session_state:
    st.session_state["view_version"] = 0

with st.sidebar:
    st.header("設定")
    
    # 【追加】表示件数リミッター
    max_items = st.number_input("1タブあたりの表示件数", min_value=100, max_value=20000, value=500, step=100, help="動作が重い場合は小さくしてください")
    
    # すでに親のパターンが選択済みの語を非表示にするトグル
    hide_redundant = st.checkbox(
        "親パターン選択済みの語を非表示", 
        value=True, 
        help="短い文字数のパターン（例: '系譜'）がすでにNG登録されている場合、それを含む長いパターン（例: '家系譜'）を画面から隠します"
    )
    
    if st.button("データ読み込み / リセット", use_container_width=True):
        if os.path.exists(DEFAULT_FILE):
            st.session_state["data_store"] = load_and_parse_csv(DEFAULT_FILE)
            st.session_state["sample_map"] = load_samples(SAMPLE_FILE)
            st.session_state["ng_selection"] = set(load_rules())
            st.session_state["view_version"] += 1
            st.rerun()
        else:
            st.error("CSVファイルがありません")

    st.divider()
    st.subheader(f"選択中: {len(st.session_state['ng_selection'])}件")
    
    if st.button("💾 rules.json に保存する", type="primary", use_container_width=True):
        success = save_rules(st.session_state["ng_selection"])
        if success:
            st.success("🎉 保存しました！")
            import time
            time.sleep(1)
            st.rerun()

    if st.button("全ての選択を解除", key="clear_all_selection", type="secondary", use_container_width=True):
        st.session_state["ng_selection"].clear()
        st.session_state["view_version"] += 1 
        st.rerun()

# --- メイン画面 ---
if st.session_state["data_store"]:
    current_ng_set = st.session_state["ng_selection"]
    sample_map = st.session_state["sample_map"]
    
    # 大タブ分け
    tab_main_select, tab_main_output = st.tabs(["🔍 末尾語彙仕分け", "📄 出力・プレビュー"])
    
    with tab_main_select:
        tab_labels = [f"Last{i}" for i in range(2, 10)]
        tabs = st.tabs(tab_labels)
        
        for tab, key in zip(tabs, tab_labels):
            with tab:
                df = st.session_state["data_store"].get(key, pd.DataFrame())
                if df.empty:
                    st.info("データなし")
                    continue

                # 【変更】ユーザー指定の上限まで表示
                limit = max_items
                is_limited = False
                if len(df) > limit:
                    is_limited = True
                    df_view = df.head(limit)
                else:
                    df_view = df

                if is_limited:
                    st.caption(f"※ 上位 {limit} 件を表示しています（全 {len(df)} 件中）")
                else:
                    st.caption(f"全 {len(df)} 件を表示しています")

                cols = st.columns(4)
                
                # 表示対象 of アイテムをフィルタリングして収集
                visible_items = []
                for _, row in df_view.iterrows():
                    word = row["Word"]
                    count = row["Count"]
                    
                    is_checked = word in current_ng_set
                    is_disabled = False
                    label_prefix = ""
                    
                    if not is_checked:
                        for parent in current_ng_set:
                            if len(parent) < len(word) and word.endswith(parent):
                                is_disabled = True
                                label_prefix = f"⛔({parent}) "
                                break
                    
                    # 非表示設定がオンで、かつ親パターンによって除外対象になっている場合はスキップ
                    if hide_redundant and is_disabled:
                        continue
                        
                    visible_items.append((word, count, is_checked, is_disabled, label_prefix))
                
                # フィルタリング後のアイテムをグリッド描画
                for idx, (word, count, is_checked, is_disabled, label_prefix) in enumerate(visible_items):
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
                    
                    unique_key = f"chk_{key}_{word}_v{st.session_state['view_version']}"
                    
                    col.checkbox(
                        label,
                        value=is_checked,
                        key=unique_key,
                        disabled=is_disabled,
                        help=tooltip,
                        on_change=toggle_ng,
                        args=(word, unique_key)
                    )

    with tab_main_output:
        st.subheader("現在のNGリストとコードプレビュー")
        final_list = sorted(list(current_ng_set))
        if final_list:
            code_text = json.dumps(final_list, ensure_ascii=False).replace('", "', '",\n    "')
            st.code(f"NOISE_PATTERNS = {code_text}", language="python")
        else:
            st.info("選択なし")

else:
    st.info("サイドバーのボタンを押してデータを読み込んでください")