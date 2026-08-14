# -*- coding: utf-8 -*-
"""
MetaClean Studio - Step 1: LLMクエリ拡張 ＆ Japan Searchメタデータ一括取得ビュー
"""
import os
import re
import time
import streamlit as st
from modules.llm_query_expander import (
    expand_query_with_llm, 
    generate_sparql_queries, 
    optimize_keywords_for_regex, 
    optimize_regex_str,
    NDC_MASTER,
    ndc_codes_to_labels,
    ndc_labels_to_codes
)
from modules.sparql_collector import fetch_uris_with_query_func, build_metadata_for_uris

def _on_rebuild_regex():
    kw_input_text = st.session_state.get("input_kw_manual", "")
    selected_ndc_labels = st.session_state.get("input_ndc_multiselect", [])
    domain_def_input = st.session_state.get("input_domain_def_manual", "")

    parsed_kws = [w.strip() for w in re.split(r"[\n,・/／]+", kw_input_text) if w.strip()]
    parsed_ndc = ndc_labels_to_codes(selected_ndc_labels)
    
    st.session_state["input_ndc_codes_manual"] = ", ".join(parsed_ndc)

    opt_kws = optimize_keywords_for_regex(parsed_kws)
    rebuilt_regex = "|".join(opt_kws)

    st.session_state["input_title_regex_manual"] = rebuilt_regex
    st.session_state["input_desc_regex_manual"] = rebuilt_regex

    exp = st.session_state.get("expansion_res", {})
    exp["keywords"] = parsed_kws
    exp["ndc_codes"] = parsed_ndc
    exp["title_regex"] = rebuilt_regex
    exp["desc_regex"] = rebuilt_regex
    exp["domain_definition"] = domain_def_input.strip()
    st.session_state["expansion_res"] = exp
    st.session_state["msg_success"] = "キーワード一覧に基づく正規表現パターンの再構築および最適化が完了しました。"


def _on_apply_manual_params():
    kw_input_text = st.session_state.get("input_kw_manual", "")
    selected_ndc_labels = st.session_state.get("input_ndc_multiselect", [])
    ndc_codes_input = st.session_state.get("input_ndc_codes_manual", "")
    title_regex_input = st.session_state.get("input_title_regex_manual", "")
    desc_regex_input = st.session_state.get("input_desc_regex_manual", "")
    domain_def_input = st.session_state.get("input_domain_def_manual", "")

    parsed_kws = [w.strip() for w in re.split(r"[\n,・/／]+", kw_input_text) if w.strip()]
    
    parsed_ndc_from_select = ndc_labels_to_codes(selected_ndc_labels)
    parsed_ndc_from_text = [c.strip() for c in re.split(r"[\n,・/／]+", ndc_codes_input) if c.strip()]
    combined_ndc = sorted(list(set(parsed_ndc_from_select + parsed_ndc_from_text)))

    auto_rebuilt_regex = "|".join(optimize_keywords_for_regex(parsed_kws))

    final_title_regex = optimize_regex_str(title_regex_input.strip()) if title_regex_input.strip() else auto_rebuilt_regex
    final_desc_regex = optimize_regex_str(desc_regex_input.strip()) if desc_regex_input.strip() else auto_rebuilt_regex

    st.session_state["input_ndc_multiselect"] = ndc_codes_to_labels(combined_ndc)
    st.session_state["input_ndc_codes_manual"] = ", ".join(combined_ndc)
    st.session_state["input_title_regex_manual"] = final_title_regex
    st.session_state["input_desc_regex_manual"] = final_desc_regex

    exp = st.session_state.get("expansion_res", {})
    exp["keywords"] = parsed_kws
    exp["ndc_codes"] = combined_ndc
    exp["title_regex"] = final_title_regex
    exp["desc_regex"] = final_desc_regex
    exp["domain_definition"] = domain_def_input.strip()
    st.session_state["expansion_res"] = exp
    st.session_state["msg_success"] = "設定パラメータの保存・適用が完了しました。"


def render_step1_view(paths: dict):
    """Step 1 画面の描画"""
    st.title("Step 1: LLMクエリ拡張およびJapan Searchメタデータ取得")
    st.caption("対象テーマに基づき、LLMを用いて異体字・旧字体・関連用語を拡張し、再現率（Recall）を最大化する検索クエリを生成してJapan Searchよりデータを一括取得します。")

    # --- 1. テーマ入力 ---
    theme_input = st.text_input(
        "対象テーマ・関心領域の指定:", 
        value="日本の古典籍における楽譜資料", 
        help="例: 日本の古典籍における楽譜資料、江戸時代の古地図、能楽演目文献 など"
    )

    # session_state の初期化（初回ロード時）
    if "expansion_res" not in st.session_state:
        words = [w.strip() for w in re.split(r"[\s,・/／におけるについて等の文献資料]+", theme_input) if len(w.strip()) >= 2]
        init_kws = words if words else [theme_input]
        opt_kws = optimize_keywords_for_regex(init_kws)
        init_regex = "|".join(opt_kws)
        
        st.session_state["expansion_res"] = {
            "theme": theme_input,
            "domain_definition": f"「{theme_input}」に関連する文化資源・文献・資料",
            "keywords": init_kws,
            "ndc_codes": [],
            "title_regex": init_regex,
            "desc_regex": init_regex,
            "is_fallback": False,
            "fallback_reason": None
        }

    # --- 2. LLMによる自動拡張セクション ---
    st.markdown("---")
    st.subheader("1. LLMによる検索キーワード・クエリ条件の自動拡張")
    st.caption("大型言語モデル（LLM）を活用し、対象テーマに関連する異体字・旧字体・ドメイン専門用語・NDC分類コードを体系的に抽出します。")

    provider_choice = st.selectbox(
        "使用するLLMプロバイダーを選択:",
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
        api_key_input = st.text_input("Google Gemini API Key:", value=env_gemini_key, type="password", help="APIキーを入力してください")
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

    if st.button("LLMによる検索キーワード・クエリ条件の自動拡張を実行", type="primary", use_container_width=True):
        with st.spinner("LLMによるドメイン分析および検索キーワードの拡張処理を実行中..."):
            expansion_res = expand_query_with_llm(
                theme_prompt=theme_input,
                provider=provider_code,
                api_base=api_base_input,
                api_key=api_key_input,
                model=model_input
            )
            st.session_state["expansion_res"] = expansion_res
            
            ndc_codes_res = expansion_res.get("ndc_codes", [])
            st.session_state["input_kw_manual"] = "\n".join(expansion_res.get("keywords", [])) if isinstance(expansion_res.get("keywords"), list) else str(expansion_res.get("keywords", ""))
            st.session_state["input_ndc_multiselect"] = ndc_codes_to_labels(ndc_codes_res)
            st.session_state["input_ndc_codes_manual"] = ", ".join(ndc_codes_res) if isinstance(ndc_codes_res, list) else str(ndc_codes_res)
            st.session_state["input_title_regex_manual"] = expansion_res.get("title_regex", "")
            st.session_state["input_desc_regex_manual"] = expansion_res.get("desc_regex", "")
            st.session_state["input_domain_def_manual"] = expansion_res.get("domain_definition", "")

            st.success("LLMによる検索キーワードおよび検索条件の自動拡張処理が完了しました。")
            st.rerun()

    exp = st.session_state["expansion_res"]

    # Widget キーの初期値が未設定の場合のみ初期値をセット
    if "input_kw_manual" not in st.session_state:
        cur_kws = exp.get("keywords", [])
        st.session_state["input_kw_manual"] = "\n".join(cur_kws) if isinstance(cur_kws, list) else str(cur_kws)
    if "input_ndc_multiselect" not in st.session_state:
        cur_ndc = exp.get("ndc_codes", [])
        st.session_state["input_ndc_multiselect"] = ndc_codes_to_labels(cur_ndc)
    if "input_ndc_codes_manual" not in st.session_state:
        cur_ndc = exp.get("ndc_codes", [])
        st.session_state["input_ndc_codes_manual"] = ", ".join(cur_ndc) if isinstance(cur_ndc, list) else str(cur_ndc)
    if "input_title_regex_manual" not in st.session_state:
        st.session_state["input_title_regex_manual"] = exp.get("title_regex", "")
    if "input_desc_regex_manual" not in st.session_state:
        st.session_state["input_desc_regex_manual"] = exp.get("desc_regex", "")
    if "input_domain_def_manual" not in st.session_state:
        st.session_state["input_domain_def_manual"] = exp.get("domain_definition", f"「{theme_input}」に関連する資料")

    # フォールバック通知表示
    if exp.get("is_fallback"):
        st.warning(
            "⚠️ LLMへの接続ができなかったため、フォールバック（ルールベース生成）が適用されました。\n"
            f"理由: `{exp.get('fallback_reason')}`"
        )

    # --- 3. 収集用検索キーワード・パラメータの手動調整セクション ---
    st.markdown("---")
    st.subheader("2. 検索キーワードおよび抽出条件の手動検証・編集")
    st.caption("LLMによって提案されたパラメータを検証し、キーワードの追加・除外、NDC分類の選択、正規表現の修正を自由に行えます。")

    c_edit1, c_edit2 = st.columns(2)
    with c_edit1:
        kw_input_text = st.text_area(
            "検索キーワード一覧 (改行またはカンマ区切り):",
            height=200,
            key="input_kw_manual"
        )
    with c_edit2:
        st.multiselect(
            "NDC (日本十進分類法) 二次区分選択リスト:",
            options=list(NDC_MASTER.values()),
            help="LLM提案の分類コードに加え、一覧から対象ドメインの分類を追加・削除できます",
            key="input_ndc_multiselect"
        )
        ndc_codes_input = st.text_input(
            "適用中 NDC 分類コード:",
            help="例: 76, 77, 18 (マルチセレクトと自動連動します)",
            key="input_ndc_codes_manual"
        )
        title_regex_input = st.text_input(
            "タイトル・主題用 正規表現 (REGEX) パターン (`|` 区切り):",
            key="input_title_regex_manual"
        )
        desc_regex_input = st.text_input(
            "内容記述 (schema:description) 用 正規表現 (REGEX) パターン (`|` 区切り):",
            key="input_desc_regex_manual"
        )

    domain_def_input = st.text_area(
        "ドメイン定義文 (Step 2-C セマンティック適合判定の評価基準):",
        height=70,
        key="input_domain_def_manual"
    )

    c_sync1, c_sync2 = st.columns([2, 1])
    with c_sync1:
        st.button(
            "キーワード一覧からの正規表現パターン自動再構築・最適化", 
            on_click=_on_rebuild_regex, 
            use_container_width=True
        )

    with c_sync2:
        st.button(
            "設定パラメータの保存・適用", 
            type="primary", 
            on_click=_on_apply_manual_params, 
            use_container_width=True
        )

    if "msg_success" in st.session_state and st.session_state["msg_success"]:
        st.success(st.session_state.pop("msg_success"))

    # --- 4. SPARQLクエリ表示 ＆ 実行セクション ---
    st.markdown("---")
    exp = st.session_state["expansion_res"]

    with st.expander("現在適用中の検索パラメータ (JSON)", expanded=False):
        st.json(exp)

    queries = generate_sparql_queries(exp)
    st.subheader(f"3. 実行対象SPARQLクエリパターン ({len(queries)} パターン)")
    st.caption("定義されたキーワード、NDC分類コード、正規表現パターンに基づき生成されたSPARQLクエリ:")

    limit_val = st.number_input("1バッチあたりの取得上限 (LIMIT):", min_value=50, max_value=1000, value=200, step=50)

    if st.button("Japan Searchからの関連メタデータ一括取得および構造化実行", type="primary", use_container_width=True):
        status_box = st.empty()
        progress_bar = st.progress(0)
        
        all_collected_uris = set()
        failed_queries = []

        # Phase 1: 一斉クエリ取得
        total_steps = len(queries)
        for idx, (name, func) in enumerate(queries):
            status_box.markdown(f"全 {len(queries)} 件中 {idx+1} 件目: `[{name}]` のメタデータを取得中...")
            uris, success = fetch_uris_with_query_func(func, pattern_name=name, limit=limit_val, timeout_sec=45)
            all_collected_uris.update(uris)
            if not success:
                failed_queries.append((name, func))
            progress_bar.progress((idx + 1) / total_steps)

        # Phase 2: 応答遅延パターンの自動再取得フェーズ
        if failed_queries:
            status_box.warning(f"初回応答遅延が発生した {len(failed_queries)} 件のクエリパターンに対して、5秒待機後に自動再読み込みを実行します...")
            time.sleep(5)
            for idx, (name, func) in enumerate(failed_queries):
                status_box.markdown(f"自動再取得フェーズ [{idx+1}/{len(failed_queries)}]: `[{name}]` を再読み込み中...")
                uris, success = fetch_uris_with_query_func(func, pattern_name=f"{name} (再試行)", limit=limit_val, timeout_sec=60)
                all_collected_uris.update(uris)
                if success:
                    st.info(f"再取得成功: `[{name}]` から追加データを正常に取得しました。")

        st.success(f"リソースURIの収集完了: 重複のない {len(all_collected_uris):,} 件の対象URIを取得しました。")
        
        with st.spinner("詳細書誌メタデータ（グラフ構造含む）の構築処理を実行中..."):
            count = build_metadata_for_uris(list(all_collected_uris), paths['PATH_RAW_METADATA'], batch_size=50)
            st.success(f"メタデータ構築完了: 全 {count:,} 件の構造化データを `{paths['PATH_RAW_METADATA']}` に保存しました。")
