# -*- coding: utf-8 -*-
"""
MetaClean Studio - Step 1: LLMクエリ超拡張 ＆ Japan Search全網羅データ自動取得ビュー (LLMメイン配置＆手動調整連動)
"""
import os
import re
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
    st.session_state["msg_success"] = "🎉 キーワード一覧から REGEX パターンを再構築・最適化しました！"


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
    st.session_state["msg_success"] = "🎉 パラメータの手動調整結果を反映しました！"


def render_step1_view(paths: dict):
    """Step 1 画面の描画"""
    st.title("Step 1: LLMクエリ超拡張 ＆ Japan Search全網羅データ自動取得")
    st.caption("自然言語テーマから旧字体・異体字・関連専門語をLLMで超拡張し、RDFタイプ制約なしでJapan Searchから母データを漏れなく全網羅（Recall最大化）取得します。")

    # --- 1. テーマ入力 ---
    theme_input = st.text_input(
        "🎯 構築したいテーマ・領域を入力してください:", 
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

    # --- 2. LLMによる自動拡張セクション (メイン機能・上部配置) ---
    st.markdown("---")
    st.subheader("🤖 LLMによるキーワード超拡張 ＆ 自動パラメータ生成")
    st.caption("LLMを活用して、対象テーマの旧字体・異体字・関連専門用語・派生語・NDC分類コードを網羅的に自動拡張します。")

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

    if st.button("✨ LLMで超拡張検索キーワード・クエリを自動生成する", type="primary", use_container_width=True):
        with st.spinner("LLMがテーマを分析し、関連語・旧字体・表記揺れを超網羅的に拡張中..."):
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

            st.success("🎉 LLMによる超拡張検索キーワードの生成処理が完了しました！")
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
            "⚠️ **【通知】LLMへの接続ができなかったため、フォールバック（ルールベース生成）を適用しました。**\n\n"
            f"・理由: `{exp.get('fallback_reason')}`"
        )

    # --- 3. 収集用検索キーワード・パラメータの手動調整セクション ---
    st.markdown("---")
    st.subheader("✏️ 収集用検索キーワード・パラメータの確認 ＆ 手動調整")
    st.caption("LLMが生成したパラメータをベースに、キーワードの追加・削除、NDC分類のリスト選択・微調整が行えます。")

    c_edit1, c_edit2 = st.columns(2)
    with c_edit1:
        kw_input_text = st.text_area(
            "📝 収集用検索キーワード一覧 (改行またはカンマ区切りで入力):",
            height=200,
            key="input_kw_manual"
        )
    with c_edit2:
        st.multiselect(
            "🏷️ NDC (日本十進分類法) 分類選択リスト (ドロップダウン選択):",
            options=list(NDC_MASTER.values()),
            help="LLM提案の分類コードに加え、リストから自由に分野を選択・追加・削除できます",
            key="input_ndc_multiselect"
        )
        ndc_codes_input = st.text_input(
            "🏷️ 適用中 NDC 分類コード (自動連動 / 手動コード入力):",
            help="例: 76, 77, 18 (マルチセレクトと相互自動連動します)",
            key="input_ndc_codes_manual"
        )
        title_regex_input = st.text_input(
            "🔍 タイトル・主題・キーワード用 REGEX パターン (`|` 区切り):",
            key="input_title_regex_manual"
        )
        desc_regex_input = st.text_input(
            "📄 説明文(description)用 REGEX パターン (`|` 区切り):",
            key="input_desc_regex_manual"
        )

    domain_def_input = st.text_area(
        "📖 資料判定用ドメイン定義文 (Step 2-C LLM適合判定の基準):",
        height=70,
        key="input_domain_def_manual"
    )

    c_sync1, c_sync2 = st.columns([2, 1])
    with c_sync1:
        st.button(
            "🔄 キーワード一覧から REGEX パターンを自動再構築・最適化する", 
            on_click=_on_rebuild_regex, 
            use_container_width=True
        )

    with c_sync2:
        st.button(
            "💾 手動調整結果を反映・適用する", 
            type="primary", 
            on_click=_on_apply_manual_params, 
            use_container_width=True
        )

    if "msg_success" in st.session_state and st.session_state["msg_success"]:
        st.success(st.session_state.pop("msg_success"))

    # --- 4. SPARQLクエリ表示 ＆ 実行セクション ---
    st.markdown("---")
    exp = st.session_state["expansion_res"]

    with st.expander("📋 現在適用中の全検索パラメータ (JSON)", expanded=False):
        st.json(exp)

    queries = generate_sparql_queries(exp)
    st.subheader(f"🔍 実行対象のSPARQLクエリパターン ({len(queries)} パターン)")
    st.caption("設定されたキーワード・分類コード・正規表現パターンに基づき、以下のSPARQLクエリを生成します。")

    limit_val = st.number_input("1バッチあたりの取得上限 (LIMIT):", min_value=50, max_value=1000, value=200, step=50)

    if st.button("🚀 Japan Search から全網羅メタデータを全自動取得・深層構築する", type="primary", use_container_width=True):
        status_box = st.empty()
        progress_bar = st.progress(0)
        
        all_collected_uris = set()
        for idx, (name, func) in enumerate(queries):
            status_box.markdown(f"⏳ パターン `[{name}]` をJapan Searchから取得中...")
            uris = fetch_uris_with_query_func(func, pattern_name=name, limit=limit_val)
            all_collected_uris.update(uris)
            progress_bar.progress((idx + 1) / len(queries))

        st.success(f"🎉 URI収集完了: 重複のない {len(all_collected_uris):,} 件のURIを取得しました！")
        
        with st.spinner("詳細書誌メタデータ（ブランクノード深層グラフ含む）を構築中..."):
            count = build_metadata_for_uris(list(all_collected_uris), paths['PATH_RAW_METADATA'], batch_size=50)
            st.success(f"🎉 メタデータ構築完了！ 全 {count:,} 件を `{paths['PATH_RAW_METADATA']}` に保存しました。")
