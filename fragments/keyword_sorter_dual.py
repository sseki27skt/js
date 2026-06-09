import streamlit as st
import pandas as pd
import json
import os
import urllib.parse

# =================設定=================
st.set_page_config(layout="wide", page_title="キーワード仕分け (スマート判定・検索付)")

INPUT_CSV = "fragments/ngram/keyword_mining_ranking.csv"
INPUT_SAMPLES = "fragments/ngram/keyword_samples.json"
OUTPUT_NG_LIST = "fragments/ngram/ng_word_list.txt"
OUTPUT_OK_LIST = "fragments/ngram/ok_word_list.txt"

# =================関数=================
def load_data():
    if not os.path.exists(INPUT_CSV): return None, None
    df = pd.read_csv(INPUT_CSV)
    samples = {}
    if os.path.exists(INPUT_SAMPLES):
        with open(INPUT_SAMPLES, 'r', encoding='utf-8') as f:
            samples = json.load(f)
    return df, samples

def load_list(filepath):
    if os.path.exists(filepath):
        with open(filepath, 'r', encoding='utf-8') as f:
            return set([line.strip() for line in f if line.strip()])
    return set()

def save_list(filepath, word_set):
    unique_words = sorted(list(word_set))
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    with open(filepath, 'w', encoding='utf-8') as f:
        for word in unique_words:
            f.write(f"{word}\n")
    return len(unique_words)

def make_google_link(word):
    query = urllib.parse.quote(f"{word} とは")
    return f"[[🔍]](https://www.google.com/search?q={query})"

# セッション初期化
if "ng_set" not in st.session_state:
    st.session_state["ng_set"] = load_list(OUTPUT_NG_LIST)
if "ok_set" not in st.session_state:
    st.session_state["ok_set"] = load_list(OUTPUT_OK_LIST)

def toggle_word(word, mode):
    if mode == "NG":
        target = st.session_state["ng_set"]
        opp = st.session_state["ok_set"]
    else:
        target = st.session_state["ok_set"]
        opp = st.session_state["ng_set"]

    if word in target:
        target.remove(word)
    else:
        target.add(word)
        if word in opp: opp.remove(word)

def bulk_action(word_list, action):
    # 一括操作の際は、グレーアウト（disabled）されているものは対象外にする必要があるが
    # ここでは簡易的に「表示されている単語リスト」に対して処理を行う
    # ただし、すでに親がいる場合はリストに入れないほうが安全かもしれないが、
    # ユーザーが明示的に押したなら追加しても良い。今回はシンプルに追加する。
    for word in word_list:
        word = str(word)
        if action == "OK":
            st.session_state["ok_set"].add(word)
            if word in st.session_state["ng_set"]: st.session_state["ng_set"].remove(word)
        elif action == "NG":
            st.session_state["ng_set"].add(word)
            if word in st.session_state["ok_set"]: st.session_state["ok_set"].remove(word)
        elif action == "RESET":
            if word in st.session_state["ok_set"]: st.session_state["ok_set"].remove(word)
            if word in st.session_state["ng_set"]: st.session_state["ng_set"].remove(word)

# =================メインUI=================
st.title("🧠 スマート・キーワード仕分けツール")
st.markdown("短い単語で判定済みのものは、自動的にグレーアウトされます。")

df, samples_map = load_data()

# --- サイドバー ---
with st.sidebar:
    st.header("設定・保存")
    mode = st.radio("クリック時の動作:", ("NG (ノイズ)", "OK (楽譜)"), index=0)
    mode_key = "NG" if "NG" in mode else "OK"
    
    st.divider()
    if st.button("💾 リストを保存・更新", type="primary"):
        c_ng = save_list(OUTPUT_NG_LIST, st.session_state["ng_set"])
        c_ok = save_list(OUTPUT_OK_LIST, st.session_state["ok_set"])
        st.success(f"保存完了！ NG:{c_ng} / OK:{c_ok}")

    st.divider()
    st.metric("⛔ NG登録数", len(st.session_state["ng_set"]))
    st.metric("✅ OK登録数", len(st.session_state["ok_set"]))

# --- メインエリア ---
if df is not None:
    search_query = st.text_input("🔍 検索 (例: '集', '譜')", "")
    
    configs = [
        {"n": "2", "label": "2文字", "col": "Bi"},
        {"n": "3", "label": "3文字", "col": "Tri"},
        {"n": "4", "label": "4文字", "col": "Tetra"},
        {"n": "5", "label": "5文字", "col": "Penta"},
    ]
    tabs = st.tabs([c["label"] for c in configs])

    # 判定用にセットをフリーズ（高速化）
    current_ng_set = st.session_state["ng_set"]
    current_ok_set = st.session_state["ok_set"]

    for conf, tab in zip(configs, tabs):
        with tab:
            col_w = f"{conf['col']}-gram"
            col_c = f"{conf['col']}-Count"
            sub_df = df[[col_w, col_c]].dropna()

            # 検索フィルタ
            if search_query:
                sub_df = sub_df[sub_df[col_w].astype(str).str.contains(search_query, na=False)]
                display_df = sub_df
                st.caption(f"検索ヒット: {len(display_df)} 件")
            else:
                display_df = sub_df.head(200)
                st.caption(f"上位 200 件を表示中")

            if display_df.empty:
                st.info("該当なし")
                continue

            # 一括操作ボタン（検索時のみ、あるいは常に表示）
            if not display_df.empty:
                with st.expander("⚡ 一括操作パネルを開く"):
                    c1, c2, c3 = st.columns(3)
                    target_words = display_df[col_w].tolist()
                    if c1.button("全部 OK", key=f"all_ok_{conf['n']}"):
                        bulk_action(target_words, "OK")
                        st.rerun()
                    if c2.button("全部 NG", key=f"all_ng_{conf['n']}"):
                        bulk_action(target_words, "NG")
                        st.rerun()
                    if c3.button("リセット", key=f"reset_{conf['n']}"):
                        bulk_action(target_words, "RESET")
                        st.rerun()

            st.divider()

            # グリッド表示
            cols = st.columns(4)
            n_samples = samples_map.get(conf["n"], {})

            for idx, row in display_df.iterrows():
                word = str(row[col_w])
                count = int(row[col_c])
                
                # --- ★スマート判定ロジック ---
                is_ng = word in current_ng_set
                is_ok = word in current_ok_set
                
                is_disabled = False
                parent_word = ""
                parent_type = "" # "OK" or "NG"

                # 自分がチェックされてない場合、親を探す
                if not (is_ng or is_ok):
                    # まずNGリストの親を探す
                    for p in current_ng_set:
                        if len(p) < len(word) and p in word:
                            is_disabled = True
                            parent_word = p
                            parent_type = "NG"
                            break
                    
                    # NGにいなければOKリストの親を探す
                    if not is_disabled:
                        for p in current_ok_set:
                            if len(p) < len(word) and p in word:
                                is_disabled = True
                                parent_word = p
                                parent_type = "OK"
                                break
                # ---------------------------

                # ラベルとスタイルの決定
                if is_ng:
                    label = f"⛔ ~~{word}~~"
                    val = True if mode_key == "NG" else False
                elif is_ok:
                    label = f"✅ **{word}**"
                    val = True if mode_key == "OK" else False
                elif is_disabled:
                    # 親がいる場合
                    if parent_type == "NG":
                        label = f"⛔({parent_word}) ~~{word}~~" # 親がNGなので自分もNG扱い
                    else:
                        label = f"✅({parent_word}) **{word}**" # 親がOKなので自分もOK扱い
                    val = False # 操作不可
                else:
                    label = f"{word}"
                    val = False

                # ツールチップ
                ex_list = n_samples.get(word, [])
                tooltip = f"【{word}】の例:\n" + "\n".join([f"・{t}" for t in ex_list]) if ex_list else "サンプルなし"
                
                # 配置
                col = cols[idx % 4]
                col.checkbox(
                    f"{label} ({count}) {make_google_link(word)}",
                    value=val,
                    key=f"chk_{conf['n']}_{idx}_{word}",
                    disabled=is_disabled, # ★ここで操作不能にする
                    help=tooltip,
                    on_change=toggle_word,
                    args=(word, mode_key)
                )

else:
    st.error("CSVファイルがありません。")