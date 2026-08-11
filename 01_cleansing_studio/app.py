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
    extract_about_keywords_from_jsonl
)
from modules.ngram_filter import extract_ngrams_from_jsonl, run_ngram_filter
from modules.llm_classifier import run_llm_semantic_classification
from modules.review_portal import load_merged_review_data, save_human_verified_data

st.set_page_config(layout="wide", page_title="MetaClean Studio")

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

menu_options = [
    "Dashboard",
    "Step 1: LLMクエリ拡張 ＆ Japan Search自動取得",
    "Step 2-A: Aboutキーワード仕分け",
    "Step 2-B: タイトル N-Gram (部分文字列 N=2〜9) 分析・仕分け",
    "Step 2-C: LLMセマンティック自動判定 (グレーゾーン分類)",
    "Step 2-D: 人間による最終査読・手動オーバーライド",
    "Step 3: データエクスポート (検索ポータル出力)"
]

choice = st.sidebar.radio("工程を選択:", menu_options)

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
                        if isinstance(about_list, dict): about_list = [about_list]
                        elif not isinstance(about_list, list): about_list = [about_list]
                        
                        kw_set = set()
                        for ab in about_list:
                            name_val = ab.get("schema:name", ab.get("@id", "")) if isinstance(ab, dict) else str(ab)
                            kw_set.add(urllib.parse.unquote(str(name_val).split('/')[-1]))

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

    # 重い集計のメモリキャッシュ化 (画面グレーアウト防止)
    @st.cache_data(show_spinner=False)
    def get_cached_about_keywords(path_mtime, path):
        return extract_about_keywords_from_jsonl(path)

    raw_mtime = os.path.getmtime(PATH_RAW_METADATA) if os.path.exists(PATH_RAW_METADATA) else 0
    about_ranking = get_cached_about_keywords(raw_mtime, PATH_RAW_METADATA)

    if not about_ranking:
        st.info("データ内に schema:about キーワードが見つかりませんでした。")
        st.stop()

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

    # --- フィルター & 検索ツールバー ---
    col_filter1, col_filter2, col_filter3 = st.columns([2, 2, 2])
    with col_filter1:
        search_query = st.text_input("🔍 キーワード絞り込み (マイナス区切りで除外):", placeholder="例: 演劇 -能")
    with col_filter2:
        hide_classified = st.checkbox("判定済みのキーワードを隠す", value=True)
    with col_filter3:
        max_items = st.number_input("表示件数の上限", min_value=30, max_value=1000, value=120, step=30)

    if "checked_words" not in st.session_state:
        st.session_state["checked_words"] = set()
    if "chk_view_ver" not in st.session_state:
        st.session_state["chk_view_ver"] = 0

    checked_words = st.session_state["checked_words"]
    chk_ver = st.session_state["chk_view_ver"]

    filtered_ranking = about_ranking
    if hide_classified:
        filtered_ranking = [(k, c) for k, c in filtered_ranking if k not in current_ng and k not in current_ok]

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

    display_items = filtered_ranking[:max_items]
    match_keywords = [k for k, c in filtered_ranking]
    selected_matches = [k for k in match_keywords if k in checked_words]

    st.markdown(f"⚡ **選択＆一括操作ツールバー** (現在絞り込まれている検索結果: **{len(filtered_ranking)} 件** | 一時チェック選択中: **{len(selected_matches)} 件**)")
    
    col_chk1, col_chk2 = st.columns([1, 1])
    with col_chk1:
        if st.button(f"☑ 検索結果 {len(match_keywords)} 件すべてにチェックを入れる", use_container_width=True):
            checked_words.update(match_keywords)
            st.session_state["chk_view_ver"] += 1
            st.rerun()
    with col_chk2:
        if st.button(f"🔳 検索結果 {len(match_keywords)} 件のチェックを外す", use_container_width=True):
            checked_words.difference_update(match_keywords)
            st.session_state["chk_view_ver"] += 1
            st.rerun()

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
            else:
                st.warning("チェックされているキーワードがありません。")

    with col_act3:
        if st.button("💾 rules.json に保存する", use_container_width=True):
            save_dict = {}
            for k in current_ng: save_dict[k] = "NG"
            for k in current_ok: save_dict[k] = "OK"
            with open(PATH_ABOUT_RULES, 'w', encoding='utf-8') as f:
                json.dump(save_dict, f, ensure_ascii=False, indent=2)
            st.success("🎉 rules.json に保存しました！")

    st.write("---")
    st.subheader(f"判定対象キーワードカード (表示中: {len(display_items)} / 該当: {len(filtered_ranking)} 件)")

    grid_cols = st.columns(3)
    sample_kws_all = [k for k, c in about_ranking[:60]]

    for idx, (kw, count) in enumerate(display_items):
        col = grid_cols[idx % 3]
        
        is_ng = kw in current_ng
        is_ok = kw in current_ok
        is_checked = kw in checked_words
        
        status_badge = " [🚫 判定済: NG]" if is_ng else (" [✅ 判定済: OK]" if is_ok else "")
        label_text = f"**{kw}** ({count}件) {make_google_link(kw)}{status_badge}"
        
        c_chk, c_pop = col.columns([6, 1])
        with c_chk:
            chk_val = st.checkbox(label_text, value=is_checked, key=f"chk_about_{kw}_v{chk_ver}")
            if chk_val != is_checked:
                if chk_val:
                    checked_words.add(kw)
                else:
                    checked_words.discard(kw)

        with c_pop:
            with st.popover("⋮", help=f"『{kw}』のメニュー"):
                st.caption(f"『{kw}』の関連提案")
                cfg = st.session_state.get("llm_config", {})
                if st.button("🚫 関連語をNG提案", key=f"btn_pop_ng_{kw}"):
                    with st.spinner("検索中..."):
                        suggs = suggest_related_keywords_by_base(
                            base_keyword=kw, 
                            mode="ng", 
                            sample_keywords=sample_kws_all,
                            provider=cfg.get("provider", "local"),
                            api_base=cfg.get("api_base", "http://localhost:1234/v1"),
                            api_key=cfg.get("api_key", ""),
                            model=cfg.get("model", "local-model")
                        )
                        st.session_state["contextual_suggs"] = {"base": kw, "mode": "ng", "suggs": suggs}
                        st.rerun()

                if st.button("✅ 関連語をOK提案", key=f"btn_pop_ok_{kw}"):
                    with st.spinner("検索中..."):
                        suggs = suggest_related_keywords_by_base(
                            base_keyword=kw, 
                            mode="ok", 
                            sample_keywords=sample_kws_all,
                            provider=cfg.get("provider", "local"),
                            api_base=cfg.get("api_base", "http://localhost:1234/v1"),
                            api_key=cfg.get("api_key", ""),
                            model=cfg.get("model", "local-model")
                        )
                        st.session_state["contextual_suggs"] = {"base": kw, "mode": "ok", "suggs": suggs}
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

    # About通過後の最新データからN-gramをマルチマイニング集計
    @st.cache_data(show_spinner=False)
    def get_cached_ngrams_from_titles(titles_tuple, min_n=2, max_n=9):
        counts = {n: Counter() for n in range(min_n, max_n + 1)}
        samples = {n: defaultdict(list) for n in range(min_n, max_n + 1)}

        for title in titles_tuple:
            clean_title = re.sub(r'[\s　\(\)（）\[\]【】「」『』\.,\d\-_]', '', title)
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

    ngram_dict = get_cached_ngrams_from_titles(tuple(input_titles))

    total_input_records = len(input_titles)
    ngram_discarded_records = 0
    if ngram_ng:
        for title in input_titles:
            if any(pattern in title for pattern in ngram_ng):
                ngram_discarded_records += 1

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

    st.write("---")

    # 一時チェックセッション管理
    if "checked_ngrams" not in st.session_state:
        st.session_state["checked_ngrams"] = set()
    if "ngram_view_ver" not in st.session_state:
        st.session_state["ngram_view_ver"] = 0

    checked_ngrams = st.session_state["checked_ngrams"]
    ngram_ver = st.session_state["ngram_view_ver"]

    # 短語(N=2等)のNG/OKパターンで判定が確定済みの親を探す関数
    def get_parent_rule(word: str, ng_set: set, ok_set: set) -> tuple:
        # まずNGリストの短語親を探す
        for ng in sorted(list(ng_set), key=len):
            if len(ng) < len(word) and ng in word:
                return "NG", ng
        # 次にOKリストの短語親を探す
        for ok in sorted(list(ok_set), key=len):
            if len(ok) < len(word) and ok in word:
                return "OK", ok
        return None, None

    # --- N=2 〜 N=9 の 8個のタブ構成 ---
    gram_tabs = st.tabs([
        "2文字 (Bi-gram)", 
        "3文字 (Tri-gram)", 
        "4文字 (Tetra-gram)", 
        "5文字 (Penta-gram)", 
        "6文字 (Hexa-gram)", 
        "7文字 (Hepta-gram)", 
        "8文字 (Octa-gram)", 
        "9文字 (Nona-gram)"
    ])

    for n_val, tab in zip(range(2, 10), gram_tabs):
        with tab:
            items_for_n = ngram_dict.get(n_val, [])
            
            # タブ内ツールバー
            col_search, col_hide, col_limit = st.columns([2, 2, 2])
            with col_search:
                q_ngram = st.text_input(f"🔍 N={n_val} 絞り込み検索:", key=f"q_ngram_{n_val}")
            with col_hide:
                hide_classified_ngram = st.checkbox(
                    "短語で判定確定済み・既知ルールを隠す", 
                    value=True, 
                    key=f"hide_ngram_{n_val}",
                    help="N=2等でNG指定した単語（例:『家譜』）を内部に含むN=3〜9の単語（例:『苗木家譜』）を画面から自動非表示にします"
                )
            with col_limit:
                limit_ngram = st.number_input("表示上限件数", min_value=30, max_value=2000, value=150, step=50, key=f"lim_ngram_{n_val}")

            # 現在のNGルールおよびOKルールにより、まだ判定が確定していない「純粋な未判定タイトル集合」をオンメモリ生成
            active_titles = [
                t for t in input_titles 
                if not any(ng in t for ng in ngram_ng) and not any(ok in t for ok in ngram_ok)
            ]

            # 各ワードの既知NG/OK控除後の未判定件数 (eff_count) を計算
            active_concat_titles = "\n".join(active_titles)
            
            filtered_items = items_for_n
            if hide_classified_ngram:
                # 短語でNG/OK判定済み(親判定OK/NG含む)、または既に他NG/OKルールで未判定件数が0件になった長語を画面から自動隠蔽
                filtered_items = [
                    (w, c, s) for w, c, s in filtered_items 
                    if w not in ngram_ng and w not in ngram_ok and get_parent_rule(w, ngram_ng, ngram_ok)[0] is None and w in active_concat_titles
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

            display_ngrams = filtered_items[:limit_ngram]
            tab_keywords = [w for w, c, s in filtered_items]
            selected_tab_matches = [w for w in tab_keywords if w in checked_ngrams]

            # ツールバー
            st.markdown(f"⚡ **N={n_val} 一括操作** (検索該当: **{len(filtered_items)} 件** | 一時チェック中: **{len(selected_tab_matches)} 件**)")
            
            c_btn1, c_btn2, c_btn3, c_btn4 = st.columns([3, 3, 3, 3])
            with c_btn1:
                if st.button(f"☑ N={n_val} 全 {len(tab_keywords)} 件にチェック", key=f"btn_chk_all_{n_val}", use_container_width=True):
                    checked_ngrams.update(tab_keywords)
                    st.session_state["ngram_view_ver"] += 1
                    st.rerun()

            with c_btn2:
                if st.button(f"🔳 N={n_val} 全件のチェック解除", key=f"btn_chk_none_{n_val}", use_container_width=True):
                    checked_ngrams.difference_update(tab_keywords)
                    st.session_state["ngram_view_ver"] += 1
                    st.rerun()

            # --- カード一覧と一括アクションを st.form で包み、チェック操作時の画面再描画を100%完全停止 ---
            with st.form(key=f"form_ngram_tab_{n_val}"):
                # ツールバー一括ボタン
                c_form1, c_form2 = st.columns(2)
                with c_form1:
                    submit_ng = st.form_submit_button(f"🚫 チェックを入れた候補を NG リストに追加", type="primary", use_container_width=True)
                with c_form2:
                    submit_ok = st.form_submit_button(f"✅ チェックを入れた候補を OK リストに追加", use_container_width=True)

                st.write("---")

                # 3カラムカード表示
                form_checkbox_values = {}
                grid_cols = st.columns(3)
                for idx, (word, count, sample_titles) in enumerate(display_ngrams):
                    col = grid_cols[idx % 3]
                    is_ng = word in ngram_ng
                    is_ok = word in ngram_ok
                    is_chk = word in checked_ngrams

                    parent_type, parent_word = get_parent_rule(word, ngram_ng, ngram_ok)

                    if is_ng:
                        status_badge = " [🚫 直接NG]"
                    elif is_ok:
                        status_badge = " [✅ 直接OK]"
                    elif parent_type == "NG":
                        status_badge = f" [🚫 NG判定済 (親: {parent_word})]"
                    elif parent_type == "OK":
                        status_badge = f" [✅ OK判定済 (親: {parent_word})]"
                    else:
                        status_badge = ""

                    # 既知のNG/OKルールにヒットしていない「未判定の残存資料」から出現例タイトルをリアルタイム動的抽出
                    active_samples = [t for t in active_titles if word in t]
                    display_samples = active_samples[:25] if active_samples else sample_titles[:25]
                    
                    sample_lines = [f"• {t}" for t in display_samples]
                    sample_header = f"未判定の出現例タイトル (未判定 {len(active_samples)}例中 {len(display_samples)}件表示):\n" if active_samples else f"出現例タイトル (既判定含む全{len(sample_titles)}例):\n"
                    sample_tooltip = sample_header + "\n".join(sample_lines)

                    # 件数表示の動的マイナス控除表記 (例: 未判定 420件 / 全686件)
                    eff_count = len(active_samples)
                    if eff_count == count:
                        count_text = f"({count}件)"
                    else:
                        count_text = f"(未判定 {eff_count}件 / 全{count}件)"
                    
                    label_text = f"「**{word}**」 {count_text} {make_google_link(word)}{status_badge}"

                    # フォーム内のチェックボックス (クリックしても全走査・再描画が100%起きない)
                    form_checkbox_values[word] = col.checkbox(
                        label_text, 
                        value=is_chk, 
                        key=f"form_chk_{n_val}_{word}_v{ngram_ver}", 
                        help=sample_tooltip
                    )

                # フォーム送信（一括追加処理）
                if submit_ng:
                    selected_in_form = [w for w, v in form_checkbox_values.items() if v]
                    if selected_in_form:
                        ngram_ng.update(selected_in_form)
                        for w in selected_in_form: ngram_ok.discard(w)
                        checked_ngrams.clear()
                        st.session_state["ngram_view_ver"] += 1
                        st.cache_data.clear()
                        st.success(f"🎉 {len(selected_in_form)} 件を NG リストに追加しました！")
                        st.rerun()
                    else:
                        st.warning("チェックされている候補がありません。")

                if submit_ok:
                    selected_in_form = [w for w, v in form_checkbox_values.items() if v]
                    if selected_in_form:
                        ngram_ok.update(selected_in_form)
                        for w in selected_in_form: ngram_ng.discard(w)
                        checked_ngrams.clear()
                        st.session_state["ngram_view_ver"] += 1
                        st.cache_data.clear()
                        st.success(f"🎉 {len(selected_in_form)} 件を OK リストに追加しました！")
                        st.rerun()
                    else:
                        st.warning("チェックされている候補がありません。")

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
    col_n1, col_n2 = st.columns(2)
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

    filter_rev = st.radio("表示フィルタ:", ["すべて", "合格のみ", "除外のみ"], horizontal=True)
    if filter_rev == "合格のみ":
        show_records = [r for r in review_records if human_decisions.get(r["id"], r["status"]) == "合格"]
    elif filter_rev == "除外のみ":
        show_records = [r for r in review_records if human_decisions.get(r["id"], r["status"]) == "除外"]
    else:
        show_records = review_records

    st.subheader(f"📑 査読対象データカード (全 {len(show_records)} / {len(review_records)} 件)")

    for idx, r in enumerate(show_records[:50]):
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

        st.success(f"🎉 エクスポート成功！ 全 {len(records):,} 件のデータを `{PATH_EXPORT_JSON}` に出力しました！")
        st.info("`02_search_viewer/index.html` をブラウザで開いて洗練されたモダンUIで検索・閲覧を行ってください。")
