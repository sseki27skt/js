# -*- coding: utf-8 -*-
"""
MetaClean Studio - 汎用文化資源メタデータ抽出 ＆ クレンジングポータル (N=2〜9 N-Gram統合版)
"""

import json
import os
import re
import time
import urllib.parse
from collections import Counter, defaultdict
import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

# モジュールインポート
from modules.llm_query_expander import expand_query_with_llm, generate_sparql_queries
from modules.sparql_collector import fetch_uris_with_query_func, build_metadata_for_uris
from modules.rule_filter import (
    run_about_filter, 
    suggest_ng_keywords_with_llm,
    suggest_related_keywords_by_base,
    extract_about_keywords_from_jsonl,
    extract_about_values
)
from modules.ngram_filter import extract_ngrams_from_jsonl, run_ngram_filter, clean_title_text
from modules.llm_classifier import run_llm_semantic_classification
from modules.review_portal import load_merged_review_data, save_human_verified_data

try:
    import streamlit_hotkeys as hotkeys
    hotkeys.activate([
        hotkeys.hk("mode_ng", "q"),
        hotkeys.hk("mode_ok", "w"),
        hotkeys.hk("mode_reset", "e"),
    ])
except Exception:
    hotkeys = None

st.set_page_config(layout="wide", page_title="MetaClean Studio")

# 画面グレーアウト・リロード時フェードを無効化するCSS
st.markdown("""
<style>
div[data-testid="stAppViewBlockContainer"] {
    opacity: 1 !important;
    transition: none !important;
}
.element-container, .stButton, div[data-st-mode="running"] {
    opacity: 1 !important;
    transition: none !important;
}
[data-testid="stStatusWidget"] {
    visibility: hidden !important;
}
</style>
""", unsafe_allow_html=True)

STUDIO_DIR = "01_cleansing_studio"
DATA_DIR = "data"
VIEWER_DIR = "02_search_viewer"
RULES_DIR = f"{STUDIO_DIR}/rules"

# データパス設定
PATH_RAW_METADATA = f"{DATA_DIR}/raw_metadata.jsonl"
PATH_TARGET_URIS = f"{DATA_DIR}/target_uris.csv"
PATH_ABOUT_RULES = f"{RULES_DIR}/about_rules.json"
PATH_NGRAM_RULES = f"{RULES_DIR}/ngram_rules.json"

PATH_ABOUT_FILTERED = f"{DATA_DIR}/about_filtered.jsonl"
PATH_NGRAM_FILTERED = f"{DATA_DIR}/ngram_filtered.jsonl"
PATH_LLM_JUDGMENTS = f"{DATA_DIR}/llm_judgments.jsonl"
PATH_VERIFIED_JSONL = f"{DATA_DIR}/human_verified_cleaned.jsonl"
PATH_EXPORT_JSON = f"{VIEWER_DIR}/scores_data.json"

st.sidebar.title("MetaClean Studio")
st.sidebar.caption("ドメインメタデータ抽出 ＆ クレンジングポータル")

step1_st = "🟢" if os.path.exists(PATH_RAW_METADATA) and os.path.getsize(PATH_RAW_METADATA) > 0 else "⚪"
step2a_st = "🟢" if os.path.exists(PATH_ABOUT_FILTERED) and os.path.getsize(PATH_ABOUT_FILTERED) > 0 else "⚪"
step2b_st = "🟢" if os.path.exists(PATH_NGRAM_FILTERED) and os.path.getsize(PATH_NGRAM_FILTERED) > 0 else "⚪"
step2c_st = "🟢" if os.path.exists(PATH_LLM_JUDGMENTS) and os.path.getsize(PATH_LLM_JUDGMENTS) > 0 else "⚪"
step2d_st = "🟢" if os.path.exists(PATH_VERIFIED_JSONL) and os.path.getsize(PATH_VERIFIED_JSONL) > 0 else "⚪"
step3_st = "🟢" if os.path.exists(PATH_EXPORT_JSON) and os.path.getsize(PATH_EXPORT_JSON) > 0 else "⚪"

menu_options = [
    "Dashboard",
    f"{step1_st} Step 1: LLMクエリ拡張 ＆ Japan Search自動取得",
    f"{step2a_st} Step 2-A: Aboutキーワード仕分け",
    f"{step2b_st} Step 2-B: タイトル N-Gram (部分文字列 N=2〜9) 分析・仕分け",
    f"{step2c_st} Step 2-C: LLMセマンティック自動判定 (グレーゾーン分類)",
    f"{step2d_st} Step 2-D: 人間による最終査読・手動オーバーライド",
    f"{step3_st} Step 3: データエクスポート (検索ポータル出力)"
]

choice_raw = st.sidebar.radio("工程を選択:", menu_options)
choice = re.sub(r'^[🟢⚪]\s*', '', choice_raw)

def count_lines(path):
    if not os.path.exists(path):
        return 0
    if path.endswith('.json'):
        try:
            with open(path, 'r', encoding='utf-8', errors='ignore') as f:
                data = json.load(f)
                return len(data) if isinstance(data, list) else 0
        except Exception:
            return 0
    else:
        with open(path, 'r', encoding='utf-8', errors='ignore') as f:
            return sum(1 for line in f if line.strip())

def make_google_link(word):
    query = urllib.parse.quote(f"{word} とは")
    url = f"https://www.google.com/search?q={query}"
    return f"[🔍]({url})"

# Dashboard
if choice == "Dashboard":
    st.title("パイプライン全体ダッシュボード")
    st.markdown("データ自動収集から多層ルールフィルタ、LLMセマンティック分類、人間査読の全進捗サマリーです。")

    cols = st.columns(4)
    with cols[0]:
        st.info("Phase 1: データ収集")
        st.metric("収集Rawメタデータ", f"{count_lines(PATH_RAW_METADATA):,} 件")

    with cols[1]:
        st.warning("Phase 2: ルールベース")
        st.metric("About フィルタ通過", f"{count_lines(PATH_ABOUT_FILTERED):,} 件")
        st.metric("N-Gram フィルタ通過", f"{count_lines(PATH_NGRAM_FILTERED):,} 件")

    with cols[2]:
        st.success("Phase 3: LLM & 査読")
        st.metric("LLM判定データ", f"{count_lines(PATH_LLM_JUDGMENTS):,} 件")
        st.metric("人間査読・確定データ", f"{count_lines(PATH_VERIFIED_JSONL):,} 件")

    with cols[3]:
        st.error("Phase 4: 成果物")
        st.metric("ポータル出力データ", f"{count_lines(PATH_EXPORT_JSON):,} 件")

# Step 1: LLMクエリ拡張 & 自動取得
elif choice == "Step 1: LLMクエリ拡張 ＆ Japan Search自動取得":
    st.title("Step 1: LLMクエリ拡張 ＆ Japan Searchデータ自動取得")
    st.markdown("LLMを活用して、探したいテーマ・ドメインの関連キーワードやNDC分類を自動拡張し、Japan Searchから全自動でメタデータを取得します。")

    theme_input = st.text_input("構築したいテーマ・領域を入力してください:", value="日本の古典籍における楽譜資料")

    st.subheader("🤖 LLMプロバイダー設定")
    provider_choice = st.selectbox(
        "使用するLLMプロバイダーを選択してください:",
        ["Google Gemini API (推奨・高速)", "LM Studio (ローカル)", "OpenAI API", "その他カスタムAPI"],
        index=0
    )

    provider_code = "local"
    api_key_input = ""
    api_base_input = "http://localhost:1234/v1"
    model_input = "gemini-3.6-flash"

    if "Google Gemini" in provider_choice:
        provider_code = "gemini"
        env_gemini_key = os.environ.get("GEMINI_API_KEY", "")
        api_key_input = st.text_input("Google Gemini API Key:", value=env_gemini_key, type="password", help="https://aistudio.google.com/ で無料取得可能")
        model_input = st.selectbox(
            "モデル選択:", 
            [
                "gemini-3.6-flash", 
                "gemini-3.5-flash", 
                "gemini-3.5-flash-lite", 
                "gemini-3.1-flash-lite", 
                "gemini-1.5-flash", 
                "gemini-1.5-pro"
            ], 
            index=0
        )
    elif "LM Studio" in provider_choice:
        provider_code = "local"
        api_base_input = st.text_input("LM Studio API エンドポイント:", value="http://localhost:1234/v1")
        model_input = st.text_input("モデル名:", value="local-model")
    elif "OpenAI" in provider_choice:
        provider_code = "openai"
        env_openai_key = os.environ.get("OPENAI_API_KEY", "")
        api_key_input = st.text_input("OpenAI API Key:", value=env_openai_key, type="password")
        api_base_input = "https://api.openai.com/v1"
        model_input = st.selectbox("モデル選択:", ["gpt-4o-mini", "gpt-4o"], index=0)

    st.session_state["llm_config"] = {
        "provider": provider_code,
        "api_base": api_base_input,
        "api_key": api_key_input,
        "model": model_input
    }

    if st.button("LLMで検索キーワード・クエリを生成する", type="primary"):
        with st.spinner("LLMがテーマを分析し、検索パラメータを拡張中..."):
            expansion_res = expand_query_with_llm(
                theme_prompt=theme_input,
                provider=provider_code,
                api_base=api_base_input,
                api_key=api_key_input,
                model=model_input
            )
            st.session_state["expansion_res"] = expansion_res
            st.success("LLMによる検索キーワード拡張処理が完了しました！")

    if "expansion_res" in st.session_state:
        exp = st.session_state["expansion_res"]
        
        if exp.get("is_fallback"):
            st.warning(
                "⚠️ **【通知】LLMへの接続ができなかったため、フォールバック（ルールベース生成）を適用しました。**\n\n"
                f"・理由: `{exp.get('fallback_reason')}`\n\n"
                "💡 **アドバイス**: Gemini API Key を入力するか、ローカルLLM（LM Studio等）を起動すると、"
                "より高度な分類コード（NDC）の自動推定や旧字体・異体字の自動拡張機能が有効になります。"
            )
        else:
            st.success(f"✨ **{provider_choice} による検索キーワード・分類パラメータの高度拡張が正常に適用されました！**")

        st.subheader("検索パラメータ提案")
        st.json(exp)

        queries = generate_sparql_queries(exp)
        st.subheader(f"生成されたSPARQLクエリ ({len(queries)} パターン)")

        limit_val = st.number_input("1バッチあたりの取得上限 (LIMIT):", min_value=50, max_value=1000, value=200)

        if st.button("Japan Search からメタデータを全自動取得・構築する", type="primary"):
            status_box = st.empty()
            progress_bar = st.progress(0)
            
            all_collected_uris = set()
            for idx, (name, func) in enumerate(queries):
                status_box.text(f"パターン [{name}] を取得中...")
                uris = fetch_uris_with_query_func(func, pattern_name=name, limit=limit_val)
                all_collected_uris.update(uris)
                progress_bar.progress((idx + 1) / len(queries))

            st.success(f"URI収集完了: ユニーク {len(all_collected_uris)} 件のURIを取得しました！")
            
            with st.spinner("詳細書誌メタデータ（ブランクノード含む）を構築中..."):
                count = build_metadata_for_uris(list(all_collected_uris), PATH_RAW_METADATA, batch_size=50)
                st.success(f"メタデータ構築完了！ 全 {count} 件を `{PATH_RAW_METADATA}` に保存しました。")

# Step 2-A: Aboutキーワード仕分け
elif choice == "Step 2-A: Aboutキーワード仕分け":
    st.title("Step 2-A: Schema:About キーワード仕分け ＆ LLMコンテキストサジェスト")
    st.markdown("収集データ内の `schema:about` キーワード一覧から、**除外すべきノイズパターン (NG)** および **保持したいパターン (OK)** を仕分けします。")

    if not os.path.exists(PATH_RAW_METADATA):
        st.warning("先に Step 1 で生メタデータ (raw_metadata.jsonl) を取得してください。")
        st.stop()

    os.makedirs(RULES_DIR, exist_ok=True)
    
    # 生データからのキーワード集計と全レコードタイトル・Aboutキャッシュ
    @st.cache_data(show_spinner=False)
    def load_raw_item_features(path):
        about_ranking = extract_about_keywords_from_jsonl(path)
        records_data = []
        if os.path.exists(path):
            with open(path, 'r', encoding='utf-8', errors='ignore') as f:
                for line in f:
                    if not line.strip(): continue
                    try:
                        item = json.loads(line)
                        about_list = item.get("schema:about", [])
                        kw_set = set(extract_about_values(about_list))

                        label_val = item.get("rdfs:label", item.get("schema:name", ""))
                        title_str = str(label_val[0]) if isinstance(label_val, list) and label_val else str(label_val)

                        records_data.append({
                            "id": item.get("@id", ""),
                            "title": title_str,
                            "about_set": kw_set
                        })
                    except Exception:
                        continue
        return about_ranking, records_data

    raw_mtime = os.path.getmtime(PATH_RAW_METADATA) if os.path.exists(PATH_RAW_METADATA) else 0
    about_ranking, raw_records = load_raw_item_features(PATH_RAW_METADATA)

    if not about_ranking:
        st.info("データ内に schema:about キーワードが見つかりませんでした。")
        st.stop()
    
    if "edited_noise" not in st.session_state:
        rules = {}
        if os.path.exists(PATH_ABOUT_RULES):
            with open(PATH_ABOUT_RULES, 'r', encoding='utf-8') as f:
                rules = json.load(f)
        st.session_state["edited_noise"] = set([k for k, v in rules.items() if v == "NG"])
        st.session_state["edited_strong"] = set([k for k, v in rules.items() if v == "OK"])

    current_ng = st.session_state["edited_noise"]
    current_ok = st.session_state["edited_strong"]

    if "checked_words" not in st.session_state:
        st.session_state["checked_words"] = set()
    if "chk_view_ver" not in st.session_state:
        st.session_state["chk_view_ver"] = 0

    checked_words = st.session_state["checked_words"]
    chk_ver = st.session_state["chk_view_ver"]



    total_about_types = len(about_ranking)
    all_kw_set = set([k for k, c in about_ranking])
    ng_classified_count = len(all_kw_set & current_ng)
    ok_classified_count = len(all_kw_set & current_ok)
    unclassified_count = total_about_types - ng_classified_count - ok_classified_count

    st.subheader("📊 Aboutキーワード分類サマリー")
    m_col1, m_col2, m_col3, m_col4 = st.columns(4)
    with m_col1:
        st.metric("トータル About種類数", f"{total_about_types:,} 種類")
    with m_col2:
        st.metric("🚫 NG (除外) 分類数", f"{ng_classified_count:,} 種類", delta=f"{ng_classified_count/max(1,total_about_types):.1%}", delta_color="inverse")
    with m_col3:
        st.metric("✅ OK (保持) 分類数", f"{ok_classified_count:,} 種類", delta=f"{ok_classified_count/max(1,total_about_types):.1%}")
    with m_col4:
        st.metric("❓ 未判定キーワード数", f"{unclassified_count:,} 種類")

    # --- 登録済み NG / OK リストの確認 ＆ 個別管理パネル ---
    # --- 登録済み NG / OK リストの確認 ＆ ボタン反転選択・一括解除パネル ---
    with st.expander(f"📋 現在の About NG / OK 登録リストを確認・管理する (🚫 NG: {len(current_ng)} 件 / ✅ OK: {len(current_ok)} 件)", expanded=False):
        c_manage_ng, c_manage_ok = st.columns(2)
        with c_manage_ng:
            st.markdown(f"### 🚫 除外(NG) リスト ({len(current_ng)} 件)")
            if current_ng:
                ng_list_sorted = sorted(list(current_ng))
                try:
                    selected_ab_ng_pills = st.pills("反転選択して削除する単語をクリック:", options=ng_list_sorted, selection_mode="multi", key="pills_about_ng")
                except AttributeError:
                    # フォールバック (st.pills 未サポート時)
                    selected_ab_ng_pills = st.multiselect("削除する単語を選択:", options=ng_list_sorted, key="ms_about_ng_fallback")

                if st.button("🗑️ 選択した単語を NG リストから登録解除（削除）", key="btn_del_ab_ng_pills", type="primary", use_container_width=True):
                    if selected_ab_ng_pills:
                        current_ng.difference_update(selected_ab_ng_pills)
                        st.session_state["chk_view_ver"] += 1
                        st.success(f"🎉 {len(selected_ab_ng_pills)} 件の単語を NG リストから削除しました！")
                        st.rerun()
                    else:
                        st.warning("解除する単語が選択されていません。上のボタンをクリックして反転選択してください。")
            else:
                st.info("NG リストは現在空です。")

        with c_manage_ok:
            st.markdown(f"### ✅ 保持(OK) リスト ({len(current_ok)} 件)")
            if current_ok:
                ok_list_sorted = sorted(list(current_ok))
                try:
                    selected_ab_ok_pills = st.pills("反転選択して削除する単語をクリック:", options=ok_list_sorted, selection_mode="multi", key="pills_about_ok")
                except AttributeError:
                    # フォールバック
                    selected_ab_ok_pills = st.multiselect("削除する単語を選択:", options=ok_list_sorted, key="ms_about_ok_fallback")

                if st.button("🗑️ 選択した単語を OK リストから登録解除（削除）", key="btn_del_ab_ok_pills", type="primary", use_container_width=True):
                    if selected_ab_ok_pills:
                        current_ok.difference_update(selected_ab_ok_pills)
                        st.session_state["chk_view_ver"] += 1
                        st.success(f"🎉 {len(selected_ab_ok_pills)} 件の単語を OK リストから削除しました！")
                        st.rerun()
                    else:
                        st.warning("解除する単語が選択されていません。上のボタンをクリックして反転選択してください。")
            else:
                st.info("OK リストは現在空です。")

    # 未判定タイトルの動的マイナス控除用データ生成
    raw_titles = [r.get("title", "") for r in raw_records if r.get("title")]
    active_records = [
        r for r in raw_records 
        if r.get("title") and not (r.get("about_set", set()) & current_ng)
    ]

    st.write("---")

    st.markdown("🎯 **【全体ノイズ検知】**: 残したい目的キーワードを指定してデータセット全体から無関係な単語を自動検出します。")
    default_targets = list(current_ok) if current_ok else st.session_state.get("expansion_res", {}).get("keywords", ["楽譜", "音楽", "音譜", "能楽", "三味線"])
    target_input = st.text_input("残したい目的(ターゲット)キーワード (カンマ区切り):", value=", ".join(default_targets))

    c_top1, c_top2 = st.columns([3, 1])
    with c_top1:
        st.caption("AI提案結果や下部のツールバーから仕分けを行ってください。")
    with c_top2:
        if st.button("🤖 全体から無関係単語をNG提案", type="primary", use_container_width=True):
            sample_kws = [k for k, c in about_ranking[:60]]
            domain_def = st.session_state.get("expansion_res", {}).get("domain_definition", "日本の文化資源・資料")
            target_kws_list = [t.strip() for t in target_input.split(",") if t.strip()]

            with st.spinner("LLMがデータセット全体からノイズ単語を分析中..."):
                cfg = st.session_state.get("llm_config", {})
                suggs = suggest_ng_keywords_with_llm(
                    current_ng_list=list(current_ng), 
                    sample_keywords=sample_kws, 
                    target_keywords=target_kws_list,
                    domain_definition=domain_def,
                    provider=cfg.get("provider", "local"),
                    api_base=cfg.get("api_base", "http://localhost:1234/v1"),
                    api_key=cfg.get("api_key", ""),
                    model=cfg.get("model", "local-model")
                )
                st.session_state["llm_about_suggs"] = suggs

    if "llm_about_suggs" in st.session_state:
        suggs = st.session_state["llm_about_suggs"]
        st.warning(f"💡 **LLMが全体検知したノイズ候補 (全 {len(suggs)} 個)**")
        selected_suggs = st.multiselect("一括登録するキーワードを選択:", options=suggs, default=suggs, key="ms_llm_suggs")
        if st.button("✨ 選択したノイズ候補をNGリストに追加", type="primary"):
            if selected_suggs:
                current_ng.update(selected_suggs)
                st.success(f"{len(selected_suggs)} 件をNGリストに追加しました！")
                st.session_state.pop("llm_about_suggs", None)
                st.rerun()

    # --- 表示オプション & 検索ツールバー ---
    st.write("---")
    st.subheader("🏷️ Aboutキーワード・ピル仕分けボード")

    col_opt1, col_opt2 = st.columns([3, 2])
    with col_opt1:
        view_filter_mode = st.radio(
            "👁️ 表示オプション:", 
            options=["🌐 すべて表示", "❓ 未判定のみ", "🚫 NGのみ", "✅ OKのみ"], 
            horizontal=True,
            key="view_filter_about_mode"
        )
        hide_zero_about = st.checkbox(
            "🙈 残存未判定件数が 0 件 (影響なし) のキーワードを非表示にする", 
            value=True, 
            key="chk_hide_zero_about",
            help="他ルールで全資料が既に除外済み（現在の未判定件数が0件）の単語を非表示にしてUIをスッキリさせます。"
        )
    with col_opt2:
        search_query = st.text_input("🔍 キーワード検索:", placeholder="例: 演劇 -能", key="q_about_pills")
    # モード切り替え初期化
    if "click_action_about_mode" not in st.session_state:
        st.session_state["click_action_about_mode"] = "🚫 NGに判定"

    st.caption("⚡ 判定モード切替 (キーボードショートカット: Q / W / E キー):")
    c_m1, c_m2, c_m3 = st.columns(3)
    
    btn1_type = "primary" if st.session_state["click_action_about_mode"] == "🚫 NGに判定" else "secondary"
    btn2_type = "primary" if st.session_state["click_action_about_mode"] == "✅ OKに判定" else "secondary"
    btn3_type = "primary" if st.session_state["click_action_about_mode"] == "🔄 未判定に戻す" else "secondary"

    b1 = c_m1.button("🔴 【 Q 】 🚫 NG判定モード", key="btn_shortcut_ab_q", type=btn1_type, use_container_width=True)
    b2 = c_m2.button("🟢 【 W 】 ✅ OK判定モード", key="btn_shortcut_ab_w", type=btn2_type, use_container_width=True)
    b3 = c_m3.button("🔵 【 E 】 🔄 未判定リセット", key="btn_shortcut_ab_e", type=btn3_type, use_container_width=True)

    if hotkeys:
        if hotkeys.pressed("mode_ng"):
            st.session_state["click_action_about_mode"] = "🚫 NGに判定"
            st.rerun()
        elif hotkeys.pressed("mode_ok"):
            st.session_state["click_action_about_mode"] = "✅ OKに判定"
            st.rerun()
        elif hotkeys.pressed("mode_reset"):
            st.session_state["click_action_about_mode"] = "🔄 未判定に戻す"
            st.rerun()

    if b1:
        st.session_state["click_action_about_mode"] = "🚫 NGに判定"
        st.rerun()
    if b2:
        st.session_state["click_action_about_mode"] = "✅ OKに判定"
        st.rerun()
    if b3:
        st.session_state["click_action_about_mode"] = "🔄 未判定に戻す"
        st.rerun()

    click_action_mode = st.session_state["click_action_about_mode"]

    # 現在のアクティブ判定モードを巨大なカラーバナーで超分かりやすく強調
    if click_action_mode == "🚫 NGに判定":
        st.error("🎯 **【現在のモード: 🚫 NG (除外) 登録モード】** (キーボード: `Q` キー) ➔ ピルボタンをクリックすると **NGリスト** に設定されます。")
    elif click_action_mode == "✅ OKに判定":
        st.success("🎯 **【現在のモード: ✅ OK (保持) 登録モード】** (キーボード: `W` キー) ➔ ピルボタンをクリックすると **OKリスト** に設定されます。")
    elif click_action_mode == "🔄 未判定に戻す":
        st.info("🎯 **【現在のモード: 🔄 未判定リセットモード】** (キーボード: `E` キー) ➔ ピルボタンをクリックすると **未判定** に戻ります。")

    # 表示フィルターの適用
    filtered_ranking = about_ranking
    if view_filter_mode == "❓ 未判定のみ":
        filtered_ranking = [(k, c) for k, c in filtered_ranking if k not in current_ng and k not in current_ok]
    elif view_filter_mode == "🚫 NGのみ":
        filtered_ranking = [(k, c) for k, c in filtered_ranking if k in current_ng]
    elif view_filter_mode == "✅ OKのみ":
        filtered_ranking = [(k, c) for k, c in filtered_ranking if k in current_ok]

    if search_query:
        parts = [p.strip() for p in re.split(r'\s+', search_query.replace('　', ' ')) if p.strip()]
        inc_words = [p.lower() for p in parts if not p.startswith('-')]
        exc_words = [p[1:].lower() for p in parts if p.startswith('-') and len(p) > 1]
        
        res_list = []
        for kw, cnt in filtered_ranking:
            kw_l = kw.lower()
            if all(i in kw_l for i in inc_words) and not any(e in kw_l for e in exc_words):
                res_list.append((kw, cnt))
        filtered_ranking = res_list

    # 爆速化: 表示対象キーワードの未判定タイトルサンプルを事前一括インデックス化 (O(1)参照)
    target_kws = [k for k, c in filtered_ranking]
    target_kws_set = set(target_kws)
    active_samples_map = defaultdict(list)
    
    # 高速走査 (schema:about に含まれるアクティブ資料を集計)
    for r in active_records:
        r_title = r.get("title", "")
        r_about = r.get("about_set", set())
        for kw in target_kws_set:
            if kw in r_about:
                active_samples_map[kw].append(r_title)

    # 残存未判定数 0件 (影響なし) の非表示フィルター
    if hide_zero_about:
        filtered_ranking = [
            (kw, cnt) for kw, cnt in filtered_ranking 
            if len(active_samples_map.get(kw, [])) > 0 or kw in current_ng or kw in current_ok
        ]

    # 仮選択セッション管理
    if "draft_about_changes" not in st.session_state:
        st.session_state["draft_about_changes"] = {}
    draft_ab = st.session_state["draft_about_changes"]

    # ツールバー & 一括確定アクションエリア
    c_hdr1, c_hdr2 = st.columns([3, 2])
    with c_hdr1:
        st.markdown(f"判定対象キーワード (該当: **{len(filtered_ranking)}** 件 | **クリックで仮選択 ➔『一括確定』ボタンで確定**)")
    with c_hdr2:
        draft_count = len(draft_ab)
        btn_apply_label = f"🚀 仮判定 ({draft_count} 件) を一括確定して適用" if draft_count > 0 else "🚀 判定を一括確定して適用"
        if st.button(btn_apply_label, type="primary" if draft_count > 0 else "secondary", use_container_width=True):
            if draft_ab:
                for kw, status in draft_ab.items():
                    if status == "NG":
                        current_ng.add(kw)
                        current_ok.discard(kw)
                    elif status == "OK":
                        current_ok.add(kw)
                        current_ng.discard(kw)
                    elif status == "RESET":
                        current_ng.discard(kw)
                        current_ok.discard(kw)
                draft_ab.clear()
                st.session_state["chk_view_ver"] += 1
                st.cache_data.clear()
                st.success("🎉 仮判定をルールへ一括適用し、件数計算を更新しました！")
                st.rerun()
            else:
                st.info("現在仮選択中のキーワードはありません。下のピルボタンをクリックして仮選択を行ってください。")

    # 4カラム・グリッドによる全件即時反応型ピル仕分けボード (出現例・マイナス件数控除付き)
    @st.fragment
    def render_about_pill_board():
        board_container = st.container(height=560)
        with board_container:
            grid_cols = st.columns(3)
            for idx, (kw, cnt) in enumerate(filtered_ranking):
                col = grid_cols[idx % 3]
                
                # 高速O(1)辞書参照
                active_samples = active_samples_map.get(kw, [])
                eff_cnt = len(active_samples)
                
                if eff_cnt == cnt:
                    cnt_str = f"({cnt}件)"
                else:
                    cnt_str = f"(未判定 {eff_cnt}件 / 全{cnt}件)"

                # ツールチップ用出現例タイトルの組み立て (先頭10件制限)
                display_samples = active_samples[:10]
                sample_lines = [f"• {t}" for t in display_samples]
                sample_header = f"【『{kw}』の未判定資料サンプル (未判定 {eff_cnt}例中 {len(display_samples)}件表示)】:\n" if display_samples else f"【『{kw}』の件数: {cnt_str}】\n"
                tooltip_txt = sample_header + "\n".join(sample_lines)

                # 仮選択状態も含めたステータス判定 (即時表示)
                draft_status = draft_ab.get(kw)
                if draft_status == "NG":
                    is_ng, is_ok = True, False
                    draft_tag = " [仮NG]"
                elif draft_status == "OK":
                    is_ng, is_ok = False, True
                    draft_tag = " [仮OK]"
                elif draft_status == "RESET":
                    is_ng, is_ok = False, False
                    draft_tag = " [仮未判定]"
                else:
                    is_ng = kw in current_ng
                    is_ok = kw in current_ok
                    draft_tag = ""

                if is_ng:
                    btn_label = f"🚫 {kw} {cnt_str}{draft_tag}"
                elif is_ok:
                    btn_label = f"✅ {kw} {cnt_str}{draft_tag}"
                else:
                    btn_label = f"❓ {kw} {cnt_str}{draft_tag}"

                # ピルボタン ＋ Google検索＆出現例確認ポップオーバーの2カラム配置
                c_btn, c_pop = col.columns([6, 1])
                with c_btn:
                    if st.button(btn_label, key=f"btn_pills_ab_{kw}_{idx}", help=tooltip_txt, use_container_width=True):
                        if click_action_mode == "🚫 NGに判定":
                            draft_ab[kw] = "NG"
                        elif click_action_mode == "✅ OKに判定":
                            draft_ab[kw] = "OK"
                        elif click_action_mode == "🔄 未判定に戻す":
                            draft_ab[kw] = "RESET"
                        st.rerun(scope="fragment")

                with c_pop:
                    with st.popover("🔍", help=f"『{kw}』の検索・詳細"):
                        st.markdown(f"### 🔍 『{kw}』")
                        st.markdown(f"- **Google検索**: {make_google_link(kw)}")
                        st.markdown(f"- **件数内訳**: 未判定 {eff_cnt} 件 / 全 {cnt} 件")
                        st.write("---")
                        st.caption("📄 **未判定の出現資料タイトル一覧 (最新10件)**:")
                        for s_title in display_samples:
                            st.markdown(f"- {s_title}")

    render_about_pill_board()

    col_act1, col_act2, col_act3 = st.columns([3, 3, 2])
    with col_act1:
        if st.button("🚫 チェック選択中のキーワードを NG リストに追加", type="primary", use_container_width=True):
            if checked_words:
                to_add = list(checked_words)
                current_ng.update(to_add)
                for k in to_add: current_ok.discard(k)
                checked_words.clear()
                st.session_state["chk_view_ver"] += 1
                st.success(f"{len(to_add)} 件のキーワードを NG リストに追加しました。")
                st.rerun()
            else:
                st.warning("チェックされているキーワードがありません。")

    with col_act2:
        if st.button("✅ チェック選択中のキーワードを OK リストに追加", use_container_width=True):
            if checked_words:
                to_add = list(checked_words)
                current_ok.update(to_add)
                for k in to_add: current_ng.discard(k)
                checked_words.clear()
                st.session_state["chk_view_ver"] += 1
                st.success(f"{len(to_add)} 件のキーワードを OK リストに追加しました。")
                st.rerun()
    st.write("---")
    c_save1, c_save2, c_reset = st.columns([2, 1, 1])
    with c_save1:
        st.caption("仕分け結果は『rules.json に保存する』ボタンを押すと次回以降も永続保持されます。")
    with c_save2:
        if st.button("💾 About rules.json に保存する", type="primary", use_container_width=True):
            save_dict = {}
            for k in current_ng: save_dict[k] = "NG"
            for k in current_ok: save_dict[k] = "OK"
            with open(PATH_ABOUT_RULES, 'w', encoding='utf-8') as f:
                json.dump(save_dict, f, ensure_ascii=False, indent=2)
            st.success("🎉 rules.json に保存しました！")

    with c_reset:
        with st.popover("🗑️ ルール全リセット", help="Aboutルールを初期化クリア"):
            st.warning("⚠️ 本当に About ルール (`about_rules.json`) を全リセットしますか？")
            st.caption("登録済みの全 NG / OK パターンおよび仮判定データが完全に消去されます。")
            if st.button("💥 確定して全リセットする", type="primary", use_container_width=True, key="btn_confirm_reset_about"):
                st.session_state["edited_noise"] = set()
                st.session_state["edited_strong"] = set()
                st.session_state["draft_about_changes"] = {}
                with open(PATH_ABOUT_RULES, 'w', encoding='utf-8') as f:
                    json.dump({}, f, ensure_ascii=False, indent=2)
                st.cache_data.clear()
                st.session_state["chk_view_ver"] += 1
                st.success("🎉 About ルール (about_rules.json) を完全にリセットしました！")
                st.rerun()

    st.write("---")
    st.subheader("▶️ About フィルタの適用実行")
    if st.button("About フィルタを実行してノイズデータを除外する", type="primary", use_container_width=True):
        save_dict = {}
        for k in current_ng: save_dict[k] = "NG"
        for k in current_ok: save_dict[k] = "OK"
        with open(PATH_ABOUT_RULES, 'w', encoding='utf-8') as f:
            json.dump(save_dict, f, ensure_ascii=False, indent=2)

        passed, disc = run_about_filter(PATH_RAW_METADATA, PATH_ABOUT_RULES, PATH_ABOUT_FILTERED, f"{DATA_DIR}/discarded_about.csv")
        st.cache_data.clear()  # メモリキャッシュを完全リフレッシュ
        st.success(f"🎉 About フィルタ適用完了: 通過 {passed} 件 / 除外 {disc} 件 (除外ログ: {DATA_DIR}/discarded_about.csv)")

# Step 2-B: タイトル N-Gram (部分文字列 N=2〜9) 分析・仕分け
elif choice == "Step 2-B: タイトル N-Gram (部分文字列 N=2〜9) 分析・仕分け":
    st.title("Step 2-B: タイトル N-Gram (部分文字列 N=2〜9) マイニング ＆ 仕分け")
    st.markdown("資料タイトルに含まれる N=2 〜 9 文字の頻出フレーズ（例: 〜日記, 〜家譜, 〜楽譜, 〜演劇 など）を集計・マイニングし、仕分けを行います。")

    # 実ディスクの about_filtered.jsonl を優先ロード、無ければ生データ＋最新ルール適用
    input_path = PATH_ABOUT_FILTERED if os.path.exists(PATH_ABOUT_FILTERED) else PATH_RAW_METADATA
    if not os.path.exists(input_path):
        st.warning("対象データが存在しません。Step 1 を実行してください。")
        st.stop()

    os.makedirs(RULES_DIR, exist_ok=True)
    if "edited_ngram_ng" not in st.session_state:
        ngram_rules = {}
        if os.path.exists(PATH_NGRAM_RULES):
            with open(PATH_NGRAM_RULES, 'r', encoding='utf-8') as f:
                ngram_rules = json.load(f)
        st.session_state["edited_ngram_ng"] = set([k for k, v in ngram_rules.items() if v == "NG"])
        st.session_state["edited_ngram_ok"] = set([k for k, v in ngram_rules.items() if v == "OK"])

    if "ngram_view_ver" not in st.session_state:
        st.session_state["ngram_view_ver"] = 0

    ngram_ng = st.session_state["edited_ngram_ng"]
    ngram_ok = st.session_state["edited_ngram_ok"]

    # 最新フィルタ済みデータソースからタイトルをロード (ファイル更新日時mtimeを監視)
    @st.cache_data(show_spinner=False)
    def load_filtered_titles(file_path, file_mtime):
        titles_data = []
        if os.path.exists(file_path):
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                for line in f:
                    if not line.strip(): continue
                    try:
                        item = json.loads(line)
                        label_val = item.get("rdfs:label", item.get("schema:name", ""))
                        title_str = str(label_val[0]) if isinstance(label_val, list) and label_val else str(label_val)
                        titles_data.append(title_str)
                    except Exception:
                        continue
        return titles_data

    input_mtime = os.path.getmtime(input_path) if os.path.exists(input_path) else 0
    input_titles = load_filtered_titles(input_path, input_mtime)

    # About通過後の最新データからN-gramをマルチマイニング集計 (軽量ファイル更新日時キー)
    @st.cache_data(show_spinner=False)
    def get_cached_ngrams_from_titles_fast(file_path, file_mtime, min_n=2, max_n=9):
        titles = load_filtered_titles(file_path, file_mtime)
        counts = {n: Counter() for n in range(min_n, max_n + 1)}
        samples = {n: defaultdict(list) for n in range(min_n, max_n + 1)}

        for title in titles:
            clean_title = clean_title_text(title)
            for n in range(min_n, max_n + 1):
                if len(clean_title) >= n:
                    ngrams = [clean_title[i:i+n] for i in range(len(clean_title) - n + 1)]
                    for word in set(ngrams):
                        counts[n][word] += 1
                        if len(samples[n][word]) < 30 and title not in samples[n][word]:
                            samples[n][word].append(title)

        result_dict = {}
        for n in range(min_n, max_n + 1):
            ranking = []
            for word, count in counts[n].most_common(500):
                if count >= 2:
                    ranking.append((word, count, samples[n][word]))
            result_dict[n] = ranking
        return result_dict

    ngram_dict = get_cached_ngrams_from_titles_fast(input_path, input_mtime)

    total_input_records = len(input_titles)

    # 除外レコード件数カウントの高速化 (NGルールハッシュキー化)
    @st.cache_data(show_spinner=False)
    def count_ngram_discarded_records(file_path, file_mtime, ng_rules_tuple):
        if not ng_rules_tuple:
            return 0
        titles = load_filtered_titles(file_path, file_mtime)
        disc_cnt = 0
        for title in titles:
            if any(pattern in title for pattern in ng_rules_tuple):
                disc_cnt += 1
        return disc_cnt

    ngram_discarded_records = count_ngram_discarded_records(input_path, input_mtime, tuple(sorted(list(ngram_ng))))
    ngram_remaining_records = total_input_records - ngram_discarded_records
    ngram_reduction_rate = (ngram_discarded_records / max(1, total_input_records))

    st.subheader("📊 N-Gramルールによる実レコード絞り込み進捗")
    ng_c1, ng_c2, ng_c3, ng_c4 = st.columns(4)
    with ng_c1:
        st.metric("📦 About通過後レコード数", f"{total_input_records:,} 件", help="Step 2-A (About仕分け) 通過済みの実資料数")
    with ng_c2:
        st.metric("🚫 N-Gram除外対象数", f"{ngram_discarded_records:,} 件", delta=f"-{ngram_reduction_rate:.1%}", delta_color="inverse")
    with ng_c3:
        st.metric("✅ 本工程通過残存レコード", f"{ngram_remaining_records:,} 件", delta=f"{ngram_remaining_records/max(1,total_input_records):.1%}")
    with ng_c4:
        st.metric("📉 本工程での絞り込み率", f"{ngram_reduction_rate:.1%} 削減")

    # --- N-Gram 登録済み NG / OK リストの確認 ＆ 個別管理パネル ---
    with st.expander(f"📋 現在の N-Gram NG / OK 登録ルールを確認・管理する (🚫 NG: {len(ngram_ng)} 件 / ✅ OK: {len(ngram_ok)} 件)", expanded=False):
        cn_manage_ng, cn_manage_ok = st.columns(2)
        with cn_manage_ng:
            st.markdown(f"### 🚫 除外(NG) N-gram パターン ({len(ngram_ng)} 件)")
            if ngram_ng:
                n_ng_sorted = sorted(list(ngram_ng))
                try:
                    selected_n_ng_pills = st.pills("反転選択して削除するパターンをクリック:", options=n_ng_sorted, selection_mode="multi", key="pills_ngram_ng")
                except AttributeError:
                    selected_n_ng_pills = st.multiselect("削除するパターンを選択:", options=n_ng_sorted, key="ms_ngram_ng_fallback")

                if st.button("🗑️ 選択したパターンを NG ルールから登録解除（削除）", key="btn_del_n_ng_pills", type="primary", use_container_width=True):
                    if selected_n_ng_pills:
                        ngram_ng.difference_update(selected_n_ng_pills)
                        st.session_state["ngram_view_ver"] += 1
                        st.cache_data.clear()
                        st.success(f"🎉 {len(selected_n_ng_pills)} 件のパターンを NG ルールから削除しました！")
                        st.rerun()
                    else:
                        st.warning("解除するパターンが選択されていません。上のボタンをクリックして反転選択してください。")
            else:
                st.info("NG N-gram ルールは現在空です。")

        with cn_manage_ok:
            st.markdown(f"### ✅ 保持(OK) N-gram パターン ({len(ngram_ok)} 件)")
            if ngram_ok:
                n_ok_sorted = sorted(list(ngram_ok))
                try:
                    selected_n_ok_pills = st.pills("反転選択して削除するパターンをクリック:", options=n_ok_sorted, selection_mode="multi", key="pills_ngram_ok")
                except AttributeError:
                    selected_n_ok_pills = st.multiselect("削除するパターンを選択:", options=n_ok_sorted, key="ms_ngram_ok_fallback")

                if st.button("🗑️ 選択したパターンを OK ルールから登録解除（削除）", key="btn_del_n_ok_pills", type="primary", use_container_width=True):
                    if selected_n_ok_pills:
                        ngram_ok.difference_update(selected_n_ok_pills)
                        st.session_state["ngram_view_ver"] += 1
                        st.cache_data.clear()
                        st.success(f"🎉 {len(selected_n_ok_pills)} 件のパターンを OK ルールから削除しました！")
                        st.rerun()
                    else:
                        st.warning("解除するパターンが選択されていません。上のボタンをクリックして反転選択してください。")
            else:
                st.info("OK N-gram ルールは現在空です。")

    # N-gram判定における未判定タイトルの動的マイナス控除用データ生成 (NG/OKルール付きキャッシュ化)
    @st.cache_data(show_spinner=False)
    def get_cached_active_titles(file_path, file_mtime, ng_rules_tuple, ok_rules_tuple=None):
        titles = load_filtered_titles(file_path, file_mtime)
        res = []
        for t in titles:
            if not t:
                continue
            if ng_rules_tuple and any(ng in t for ng in ng_rules_tuple):
                continue
            if ok_rules_tuple and any(ok in t for ok in ok_rules_tuple):
                continue
            res.append(t)
        return res

    active_titles = get_cached_active_titles(
        input_path, 
        input_mtime, 
        tuple(sorted(list(ngram_ng))),
        tuple(sorted(list(ngram_ok)))
    )

    # 短語(N=2等)のNG/OKパターンで判定が確定済みの親を探す関数
    def get_parent_rule(word: str, ng_set: set, ok_set: set) -> tuple:
        for ng in sorted(list(ng_set), key=len):
            if len(ng) < len(word) and ng in word:
                return "NG", ng
        for ok in sorted(list(ok_set), key=len):
            if len(ok) < len(word) and ok in word:
                return "OK", ok
        return None, None

    # N選択セグメントコントローラー (全タブ4,000件一括描画フリーズを防ぐオンデマンド爆速描画)
    n_options = [
        "2文字 (Bi-gram)", 
        "3文字 (Tri-gram)", 
        "4文字 (Tetra-gram)", 
        "5文字 (Penta-gram)", 
        "6文字 (Hexa-gram)", 
        "7文字 (Hepta-gram)", 
        "8文字 (Octa-gram)", 
        "9文字 (Nona-gram)"
    ]
    
    selected_n_str = st.radio("🎯 分析対象の N-gram (文字数) を選択:", options=n_options, horizontal=True, key="selected_n_gram_radio")
    n_val = int(selected_n_str.split("文字")[0])

    items_for_n = ngram_dict.get(n_val, [])

    # モード切り替え初期化
    if "c_mode_ngram_shared" not in st.session_state:
        st.session_state["c_mode_ngram_shared"] = "🚫 NGに判定"

    # タブ内ツールバー & 表示オプション
    col_n_opt1, col_n_opt2 = st.columns([3, 2])
    with col_n_opt1:
        v_mode_n = st.radio(
            "👁️ 表示オプション:", 
            options=["🌐 すべて表示", "❓ 未判定のみ", "🚫 NGのみ", "✅ OKのみ"], 
            horizontal=True,
            key="v_mode_ngram_shared"
        )
        hide_zero_ngram = st.checkbox(
            "🙈 残存未判定件数が 0 件 (影響なし) の N-Gram パターンを非表示にする", 
            value=True, 
            key="chk_hide_zero_ngram_shared",
            help="他ルールで全資料が既に除外済み（現在の未判定件数が0件）のパターンを非表示にしてUIをスッキリさせます。"
        )
    with col_n_opt2:
        q_ngram = st.text_input("🔍 N-Gram 検索:", key="q_ngram_shared")

    st.caption("⚡ N-gram 判定モード切替 (キーボードショートカット: Q / W / E キー):")
    cn_m1, cn_m2, cn_m3 = st.columns(3)
    
    n_btn1_t = "primary" if st.session_state["c_mode_ngram_shared"] == "🚫 NGに判定" else "secondary"
    n_btn2_t = "primary" if st.session_state["c_mode_ngram_shared"] == "✅ OKに判定" else "secondary"
    n_btn3_t = "primary" if st.session_state["c_mode_ngram_shared"] == "🔄 未判定に戻す" else "secondary"

    bn1 = cn_m1.button("🔴 【 Q 】 🚫 NG判定モード", key="btn_mq_n_shared", use_container_width=True, type=n_btn1_t)
    bn2 = cn_m2.button("🟢 【 W 】 ✅ OK判定モード", key="btn_mw_n_shared", use_container_width=True, type=n_btn2_t)
    bn3 = cn_m3.button("🔵 【 E 】 🔄 未判定リセット", key="btn_me_n_shared", use_container_width=True, type=n_btn3_t)

    if hotkeys:
        if hotkeys.pressed("mode_ng"):
            st.session_state["c_mode_ngram_shared"] = "🚫 NGに判定"
            st.rerun()
        elif hotkeys.pressed("mode_ok"):
            st.session_state["c_mode_ngram_shared"] = "✅ OKに判定"
            st.rerun()
        elif hotkeys.pressed("mode_reset"):
            st.session_state["c_mode_ngram_shared"] = "🔄 未判定に戻す"
            st.rerun()

    if bn1:
        st.session_state["c_mode_ngram_shared"] = "🚫 NGに判定"
        st.rerun()
    if bn2:
        st.session_state["c_mode_ngram_shared"] = "✅ OKに判定"
        st.rerun()
    if bn3:
        st.session_state["c_mode_ngram_shared"] = "🔄 未判定に戻す"
        st.rerun()

    c_mode_n = st.session_state["c_mode_ngram_shared"]

    # アクティブ判定モードの強調バナー
    if c_mode_n == "🚫 NGに判定":
        st.error("🎯 **【現在のモード: 🚫 NG (除外) 登録モード】** ➔ N-gramピルをクリックすると **NGリスト** に登録されます。")
    elif c_mode_n == "✅ OKに判定":
        st.success("🎯 **【現在のモード: ✅ OK (保持) 登録モード】** ➔ N-gramピルをクリックすると **OKリスト** に登録されます。")
    elif c_mode_n == "🔄 未判定に戻す":
        st.info("🎯 **【現在のモード: 🔄 未判定リセットモード】** ➔ N-gramピルをクリックすると 判定がクリアされます。")

    # 表示フィルター適用
    filtered_items = items_for_n
    if v_mode_n == "❓ 未判定のみ":
        filtered_items = [
            (w, c, s) for w, c, s in filtered_items 
            if w not in ngram_ng and w not in ngram_ok and get_parent_rule(w, ngram_ng, ngram_ok)[0] is None
        ]
    elif v_mode_n == "🚫 NGのみ":
        filtered_items = [
            (w, c, s) for w, c, s in filtered_items 
            if w in ngram_ng or get_parent_rule(w, ngram_ng, ngram_ok)[0] == "NG"
        ]
    elif v_mode_n == "✅ OKのみ":
        filtered_items = [
            (w, c, s) for w, c, s in filtered_items 
            if w in ngram_ok or get_parent_rule(w, ngram_ng, ngram_ok)[0] == "OK"
        ]

    if q_ngram:
        parts = [p.strip() for p in re.split(r'\s+', q_ngram.replace('　', ' ')) if p.strip()]
        inc_words = [p.lower() for p in parts if not p.startswith('-')]
        exc_words = [p[1:].lower() for p in parts if p.startswith('-') and len(p) > 1]
        
        res_l = []
        for w, c, s in filtered_items:
            w_l = w.lower()
            if all(i in w_l for i in inc_words) and not any(e in w_l for e in exc_words):
                res_l.append((w, c, s))
        filtered_items = res_l

    # 爆速化: 表示対象N-gramパターンの未判定タイトルサンプルを事前一括インデックス化 (キャッシュ関数)
    @st.cache_data(show_spinner=False)
    def get_cached_n_samples_map(active_titles_tuple, target_words_tuple):
        target_words_set = set(target_words_tuple)
        samples_map = defaultdict(list)
        for t in active_titles_tuple:
            clean_t = clean_title_text(t)
            for w in target_words_set:
                if w in clean_t:
                    samples_map[w].append(t)
        return samples_map

    target_words_tuple = tuple(w for w, c, s in filtered_items)
    active_n_samples_map = get_cached_n_samples_map(tuple(active_titles), target_words_tuple)

    # 残存未判定数 0件 (影響なし) の非表示フィルター
    if hide_zero_ngram:
        filtered_items = [
            (w, c, s) for w, c, s in filtered_items 
            if len(active_n_samples_map.get(w, [])) > 0 or w in ngram_ng or w in ngram_ok
        ]

    # 仮選択セッション管理
    if f"draft_n_{n_val}_changes" not in st.session_state:
        st.session_state[f"draft_n_{n_val}_changes"] = {}
    draft_n = st.session_state[f"draft_n_{n_val}_changes"]

    # ツールバー & 一括確定エリア
    cn_hdr1, cn_hdr2 = st.columns([3, 2])
    with cn_hdr1:
        st.markdown(f"N={n_val} パターン一覧 (該当: **{len(filtered_items)}** 件 | **クリックで仮選択 ➔『一括確定』で確定**)")
    with cn_hdr2:
        draft_n_cnt = len(draft_n)
        btn_n_apply_label = f"🚀 N={n_val} 仮判定 ({draft_n_cnt} 件) を一括確定して適用" if draft_n_cnt > 0 else f"🚀 N={n_val} 判定を一括確定して適用"
        if st.button(btn_n_apply_label, key=f"btn_apply_n_{n_val}", type="primary" if draft_n_cnt > 0 else "secondary", use_container_width=True):
            if draft_n:
                for w, status in draft_n.items():
                    if status == "NG":
                        ngram_ng.add(w)
                        ngram_ok.discard(w)
                    elif status == "OK":
                        ngram_ok.add(w)
                        ngram_ng.discard(w)
                    elif status == "RESET":
                        ngram_ng.discard(w)
                        ngram_ok.discard(w)
                draft_n.clear()
                st.session_state["ngram_view_ver"] += 1
                st.cache_data.clear()
                st.success(f"🎉 N={n_val} の仮判定をルールへ一括適用し、件数計算を更新しました！")
                st.rerun()
            else:
                st.info("現在仮選択中のパターンはありません。下のピルボタンをクリックして仮選択を行ってください。")

    # 全件スクロール表示対応ピルボードコンテナ (出現例・マイナス件数控除付き)
    @st.fragment
    def render_ngram_pill_board():
        n_board_container = st.container(height=560)
        with n_board_container:
            cols_n = st.columns(3)
            for idx, (w, c, s) in enumerate(filtered_items):
                col = cols_n[idx % 3]
                parent_type, parent_word = get_parent_rule(w, ngram_ng, ngram_ok)
                
                # 高速O(1)辞書参照
                active_samples = active_n_samples_map.get(w, [])
                eff_c = len(active_samples)
                
                if eff_c == c:
                    c_text = f"({c}件)"
                else:
                    c_text = f"(未判定 {eff_c}件 / 全{c}件)"

                # ツールチップ用出現例タイトルの組み立て (先頭10件制限)
                display_samples = active_samples[:10] if active_samples else s[:10]
                sample_lines = [f"• {t}" for t in display_samples]
                sample_header = f"【『{w}』の未判定資料サンプル (未判定 {eff_c}例中 {len(display_samples)}件表示)】:\n" if display_samples else f"【『{w}』の件数: {c_text}】\n"
                n_tooltip = sample_header + "\n".join(sample_lines)

                # 仮選択状態も含めたステータス判定 (即時表示)
                draft_n_status = draft_n.get(w)
                if draft_n_status == "NG":
                    is_n_ng, is_n_ok = True, False
                    d_tag = " [仮NG]"
                elif draft_n_status == "OK":
                    is_n_ng, is_n_ok = False, True
                    d_tag = " [仮OK]"
                elif draft_n_status == "RESET":
                    is_n_ng, is_n_ok = False, False
                    d_tag = " [仮未判定]"
                else:
                    is_n_ng = w in ngram_ng
                    is_n_ok = w in ngram_ok
                    d_tag = ""

                if is_n_ng:
                    btn_txt = f"🚫 {w} {c_text}{d_tag}"
                elif is_n_ok:
                    btn_txt = f"✅ {w} {c_text}{d_tag}"
                elif parent_type == "NG":
                    btn_txt = f"🚫 {w} [親:{parent_word}] {c_text}{d_tag}"
                elif parent_type == "OK":
                    btn_txt = f"✅ {w} [親:{parent_word}] {c_text}{d_tag}"
                else:
                    btn_txt = f"❓ {w} {c_text}{d_tag}"

                c_btn_n, c_pop_n = col.columns([6, 1])
                with c_btn_n:
                    if st.button(btn_txt, key=f"btn_pills_n_{n_val}_{w}_{idx}", help=n_tooltip, use_container_width=True):
                        if c_mode_n == "🚫 NGに判定":
                            draft_n[w] = "NG"
                        elif c_mode_n == "✅ OKに判定":
                            draft_n[w] = "OK"
                        elif c_mode_n == "🔄 未判定に戻す":
                            draft_n[w] = "RESET"
                        st.rerun(scope="fragment")

                with c_pop_n:
                    with st.popover("🔍", help=f"『{w}』の検索・詳細"):
                        st.markdown(f"### 🔍 『{w}』")
                        st.markdown(f"- **Google検索**: {make_google_link(w)}")
                        st.markdown(f"- **件数内訳**: 未判定 {eff_c} 件 / 全 {c} 件")
                        if parent_type:
                            st.info(f"親ルール継承: **{parent_type}** (親パターン: 『{parent_word}』)")
                        st.write("---")
                        st.caption("📄 **未判定の出現資料タイトル一覧 (最新10件)**:")
                        for s_title in display_samples:
                            st.markdown(f"- {s_title}")

    render_ngram_pill_board()


    # 親単語の指定 (謡本=OK, 家譜=NG など) を全N-gramパターンの長語へ自動継承補完するヘルパー
    def build_expanded_ngram_rules(ng_set, ok_set, all_ngram_dict):
        final_dict = {}
        for w in ng_set: final_dict[w] = "NG"
        for w in ok_set: final_dict[w] = "OK"

        # 全N=2〜9の抽出単語に対し、親単語がOK/NGにあれば自動補完
        for n_val, items in all_ngram_dict.items():
            for word, count, _ in items:
                if word in final_dict:
                    continue
                p_type, p_word = get_parent_rule(word, ng_set, ok_set)
                if p_type:
                    final_dict[word] = p_type
        return final_dict

    st.write("---")
    col_n1, col_n2, col_n3 = st.columns([2, 2, 1])
    with col_n1:
        if st.button("💾 N-Gram ルールを保存する", type="primary", use_container_width=True):
            save_dict = build_expanded_ngram_rules(ngram_ng, ngram_ok, ngram_dict)
            with open(PATH_NGRAM_RULES, 'w', encoding='utf-8') as f:
                json.dump(save_dict, f, ensure_ascii=False, indent=2)
            st.success(f"N-Gram ルールを保存しました！ (直接指定＋自動継承補完: 全 {len(save_dict):,} ルール)")

    with col_n2:
        if st.button("▶️ N-Gram フィルタを実行する", type="primary", use_container_width=True):
            save_dict = build_expanded_ngram_rules(ngram_ng, ngram_ok, ngram_dict)
            with open(PATH_NGRAM_RULES, 'w', encoding='utf-8') as f:
                json.dump(save_dict, f, ensure_ascii=False, indent=2)

            passed, disc = run_ngram_filter(input_path, PATH_NGRAM_RULES, PATH_NGRAM_FILTERED, f"{DATA_DIR}/discarded_ngram.csv")
            st.success(f"N-Gram フィルタ完了: 通過 {passed} 件 / 除外 {disc} 件 (除外ログ: {DATA_DIR}/discarded_ngram.csv)")

    with col_n3:
        with st.popover("🗑️ ルール全リセット", help="N-Gramルールを初期化クリア"):
            st.warning("⚠️ 本当に N-Gram ルール (`ngram_rules.json`) を全リセットしますか？")
            st.caption("登録済みの全 N-gram NG / OK パターンおよび仮判定データが完全に消去されます。")
            if st.button("💥 確定して全リセットする", type="primary", use_container_width=True, key="btn_confirm_reset_ngram"):
                st.session_state["edited_ngram_ng"] = set()
                st.session_state["edited_ngram_ok"] = set()
                for key in list(st.session_state.keys()):
                    if key.startswith("draft_n_"):
                        st.session_state[key] = {}
                with open(PATH_NGRAM_RULES, 'w', encoding='utf-8') as f:
                    json.dump({}, f, ensure_ascii=False, indent=2)
                st.cache_data.clear()
                st.session_state["ngram_view_ver"] += 1
                st.success("🎉 N-Gram ルール (ngram_rules.json) を完全にリセットしました！")
                st.rerun()

# Step 2-C: LLMセマンティック自動判定
elif choice == "Step 2-C: LLMセマンティック自動判定 (グレーゾーン分類)":
    st.title("Step 2-C: LLMセマンティック自動判定 (グレーゾーン分類)")
    st.markdown("ルールベースで判定しきれなかったデータに対し、Gemini API / LLM がタイトル・詳細記述から**理由付きで自動判定**を行います。")

    input_path = PATH_NGRAM_FILTERED if os.path.exists(PATH_NGRAM_FILTERED) else (PATH_ABOUT_FILTERED if os.path.exists(PATH_ABOUT_FILTERED) else PATH_RAW_METADATA)
    if not os.path.exists(input_path):
        st.warning("対象データが存在しません。前のステップを実行してください。")
        st.stop()

    cfg = st.session_state.get("llm_config", {})
    st.info(f"使用プロバイダー: **{cfg.get('provider', 'gemini')}** | モデル: **{cfg.get('model', 'gemini-3.6-flash')}**")

    domain_def = st.session_state.get("expansion_res", {}).get("domain_definition", "日本の古典籍における楽譜・音楽資料")
    limit_val = st.number_input("判定処理件数の上限 (テスト実行用):", min_value=5, max_value=5000, value=30, step=10)

    if st.button("🤖 LLMセマンティック自動判定を開始する", type="primary"):
        progress_bar = st.progress(0)
        status_text = st.empty()

        def on_progress(current, total, title, is_target, reason):
            progress_bar.progress(current / total)
            badge = "✅ 適合" if is_target is True else ("🚫 非適合" if is_target is False else "❓ 不明")
            status_text.markdown(f"[{current}/{total}] {badge} **{title[:30]}** - *{reason}*")

        acc, rej, unk = run_llm_semantic_classification(
            input_jsonl_path=input_path,
            output_judgments_path=PATH_LLM_JUDGMENTS,
            domain_definition=domain_def,
            provider=cfg.get("provider", "gemini"),
            api_base=cfg.get("api_base", "http://localhost:1234/v1"),
            api_key=cfg.get("api_key", ""),
            model=cfg.get("model", "gemini-3.6-flash"),
            limit=limit_val,
            progress_callback=on_progress
        )

        st.success(f"LLM自動判定完了！ 適合: {acc} 件 / 非適合: {rej} 件 / 不明: {unk} 件 (判定ログ: `{PATH_LLM_JUDGMENTS}`)")

# Step 2-D: 人間による最終査読・手動オーバーライド
elif choice == "Step 2-D: 人間による最終査読・手動オーバーライド":
    st.title("Step 2-D: 人間による最終査読・手動オーバーライド ポータル")
    st.markdown("全フェーズ（About, N-Gram, LLM判定）の結果と理由を確認し、判定誤りを手動でオーバーライド（合格 ⇄ 除外）修正できます。")

    if not os.path.exists(PATH_RAW_METADATA):
        st.warning("生メタデータが存在しません。Step 1 を実行してください。")
        st.stop()

    with st.spinner("全フェーズの判定結果と理由を集約中..."):
        review_records = load_merged_review_data(
            raw_jsonl_path=PATH_RAW_METADATA,
            about_filtered_path=PATH_ABOUT_FILTERED,
            suffix_filtered_path=None,
            ngram_filtered_path=PATH_NGRAM_FILTERED,
            llm_judgments_path=PATH_LLM_JUDGMENTS
        )

    if "human_decisions" not in st.session_state:
        st.session_state["human_decisions"] = {r["id"]: r["status"] for r in review_records}

    human_decisions = st.session_state["human_decisions"]

    c_f1, c_f2 = st.columns([2, 3])
    with c_f1:
        filter_rev = st.radio("表示フィルタ:", ["すべて", "合格のみ", "除外のみ"], horizontal=True, key="filter_rev_portal")
    with c_f2:
        search_rev = st.text_input("🔍 タイトル / URI / 理由で検索:", placeholder="例: 楽譜 または LLM判定除外", key="search_rev_portal")

    if filter_rev == "合格のみ":
        show_records = [r for r in review_records if human_decisions.get(r["id"], r["status"]) == "合格"]
    elif filter_rev == "除外のみ":
        show_records = [r for r in review_records if human_decisions.get(r["id"], r["status"]) == "除外"]
    else:
        show_records = review_records

    if search_rev.strip():
        s_query = search_rev.strip().lower()
        show_records = [
            r for r in show_records
            if s_query in r["title"].lower() or s_query in r["id"].lower() or s_query in r["reasons"].lower() or s_query in r.get("llm_reason", "").lower()
        ]

    total_show = len(show_records)
    page_size = 50
    total_pages = max(1, (total_show + page_size - 1) // page_size)

    if "rev_page" not in st.session_state:
        st.session_state["rev_page"] = 1

    c_p1, c_p2 = st.columns([3, 2])
    with c_p1:
        st.subheader(f"📑 査読対象データカード (該当: {total_show:,} / 全 {len(review_records):,} 件)")
    with c_p2:
        if total_pages > 1:
            current_page = st.number_input(f"ページ移動 (1〜{total_pages}):", min_value=1, max_value=total_pages, value=min(st.session_state["rev_page"], total_pages), step=1, key="num_input_rev_page")
        else:
            current_page = 1

    start_idx = (current_page - 1) * page_size
    end_idx = min(start_idx + page_size, total_show)
    page_records = show_records[start_idx:end_idx]

    st.caption(f"表示中: {start_idx + 1:,} 〜 {end_idx:,} 件目 (全 {total_pages} ページ)")

    for idx, r in enumerate(page_records):
        rid = r["id"]
        cur_status = human_decisions.get(rid, r["status"])

        with st.expander(f"{'✅ [合格]' if cur_status == '合格' else '🚫 [除外]'} **{r['title']}** (理由: {r['reasons']})"):
            c_info, c_action = st.columns([4, 1])
            with c_info:
                st.write(f"**URI**: [{rid}]({rid})")
                st.write(f"**自動判定理由**: `{r['reasons']}`")
                if r.get("llm_reason"):
                    st.info(f"🤖 LLM判定理由: {r['llm_reason']}")
            with c_action:
                new_val = st.radio(
                    "人間最終判定:",
                    ["合格", "除外"],
                    index=0 if cur_status == "合格" else 1,
                    key=f"rad_rev_{rid}"
                )
                if new_val != cur_status:
                    human_decisions[rid] = new_val
                    st.rerun()

    st.write("---")
    if st.button("💾 人間査読データ (`human_verified_cleaned.jsonl`) を最終確定保存する", type="primary", use_container_width=True):
        count = save_human_verified_data(review_records, human_decisions, PATH_VERIFIED_JSONL)
        st.success(f"人間査読完了！ 全 {count} 件の通過データを `{PATH_VERIFIED_JSONL}` に最終確定保存しました！")

# Step 3: データエクスポート
elif choice == "Step 3: データエクスポート (検索ポータル出力)":
    st.title("Step 3: 検索ポータル用データエクスポート")
    st.markdown("クレンジングされた最終データを `02_search_viewer` 用の静的JSONへ書き出し、モダン検索UIで即時検索可能にします。")

    source_path = PATH_VERIFIED_JSONL if os.path.exists(PATH_VERIFIED_JSONL) else (
        PATH_NGRAM_FILTERED if os.path.exists(PATH_NGRAM_FILTERED) else (
            PATH_ABOUT_FILTERED if os.path.exists(PATH_ABOUT_FILTERED) else PATH_RAW_METADATA
        )
    )
    if not os.path.exists(source_path):
        st.warning("エクスポート対象データが存在しません。Step 1 でメタデータを取得してください。")
        st.stop()

    source_line_count = count_lines(source_path)
    st.info(f"📂 検出された最新データソース: `{source_path}` (全 {source_line_count:,} 件)")

    if st.button("検索ポータル用 `scores_data.json` をビルド・エクスポートする", type="primary", use_container_width=True):
        records = []
        with open(source_path, 'r', encoding='utf-8') as f:
            for line in f:
                if not line.strip(): continue
                try:
                    data = json.loads(line)
                    
                    label = data.get('rdfs:label', data.get('schema:name', 'No Title'))
                    title = label[0] if isinstance(label, list) and label else str(label)
                    
                    desc_val = data.get('schema:description', '')
                    desc = desc_val[0] if isinstance(desc_val, list) and desc_val else str(desc_val)
                    
                    provider = ''
                    source = data.get('https://jpsearch.go.jp/term/property#sourceInfo', {})
                    if isinstance(source, dict):
                        provider = str(source.get('schema:provider', '')).split('/')[-1]

                    genre = "古典資料/その他"
                    if any(k in title for k in ["雅楽", "笙", "篳篥"]): genre = "雅楽"
                    elif any(k in title for k in ["謡", "能", "観世"]): genre = "能楽/謡曲"
                    elif any(k in title for k in ["三味線", "長唄", "地歌"]): genre = "三味線音楽"

                    item_id = data.get('@id', data.get('id', ''))
                    records.append({
                        "id": item_id,
                        "title": title,
                        "description": desc[:300] if desc else "詳細記述なし",
                        "provider": provider or "Japan Search",
                        "genre": genre,
                        "url": item_id
                    })
                except Exception:
                    continue

        os.makedirs(os.path.dirname(PATH_EXPORT_JSON), exist_ok=True)
        with open(PATH_EXPORT_JSON, 'w', encoding='utf-8') as jf:
            json.dump(records, jf, ensure_ascii=False, indent=2)

        # CSV 出力
        path_export_csv = f"{DATA_DIR}/cleaned_metadata.csv"
        df_export = pd.DataFrame(records)
        df_export.to_csv(path_export_csv, index=False, encoding='utf-8-sig')

        st.success(f"🎉 エクスポート成功！ 全 {len(records):,} 件のデータを `{PATH_EXPORT_JSON}` および `{path_export_csv}` に出力しました！")
        st.info("`02_search_viewer/index.html` をブラウザで開いて洗練されたモダンUIで検索・閲覧を行ってください。")

    st.write("---")
    st.subheader("📥 成果物データのブラウザ直接ダウンロード")
    st.markdown("生成されたクレンジング結果ファイルをワンクリックでローカルPCへダウンロードできます。")

    c_dl1, c_dl2, c_dl3 = st.columns(3)
    path_export_csv = f"{DATA_DIR}/cleaned_metadata.csv"

    with c_dl1:
        if os.path.exists(PATH_EXPORT_JSON):
            with open(PATH_EXPORT_JSON, 'rb') as f:
                st.download_button(
                    label="📥 scores_data.json をダウンロード",
                    data=f,
                    file_name="scores_data.json",
                    mime="application/json",
                    use_container_width=True
                )
        else:
            st.button("📥 scores_data.json (未出力)", disabled=True, use_container_width=True)

    with c_dl2:
        if os.path.exists(path_export_csv):
            with open(path_export_csv, 'rb') as f:
                st.download_button(
                    label="📥 cleaned_metadata.csv をダウンロード",
                    data=f,
                    file_name="cleaned_metadata.csv",
                    mime="text/csv",
                    use_container_width=True
                )
        else:
            st.button("📥 cleaned_metadata.csv (未出力)", disabled=True, use_container_width=True)

    with c_dl3:
        if os.path.exists(PATH_VERIFIED_JSONL):
            with open(PATH_VERIFIED_JSONL, 'rb') as f:
                st.download_button(
                    label="📥 human_verified_cleaned.jsonl をダウンロード",
                    data=f,
                    file_name="human_verified_cleaned.jsonl",
                    mime="application/jsonlines",
                    use_container_width=True
                )
        else:
            st.button("📥 human_verified_cleaned.jsonl (未確定)", disabled=True, use_container_width=True)
