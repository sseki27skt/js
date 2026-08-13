# -*- coding: utf-8 -*-
"""
MetaClean Studio - Step 1: LLMクエリ拡張 ＆ Japan Search自動取得ビュー
"""
import os
import streamlit as st
from modules.llm_query_expander import expand_query_with_llm, generate_sparql_queries
from modules.sparql_collector import fetch_uris_with_query_func, build_metadata_for_uris

def render_step1_view(paths: dict):
    """Step 1 画面の描画"""
    st.title("Step 1: LLMクエリ拡張 ＆ Japan Searchデータ自動取得")
    st.caption("自然言語テーマからNDC分類・キーワード・SPARQLパターンをLLMで自動展開し、Japan Searchから深層メタデータを構築します。")

    theme_input = st.text_input(
        "🎯 構築したいテーマ・領域を入力してください:", 
        value="日本の古典籍における楽譜資料", 
        help="例: 日本の古典籍における楽譜資料、江戸時代の古地図、能楽演目文献 など"
    )

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

    if st.button("✨ LLMで検索キーワード・クエリを自動生成する", type="primary", use_container_width=True):
        with st.spinner("LLMがテーマを分析し、検索パラメータを拡張中..."):
            expansion_res = expand_query_with_llm(
                theme_prompt=theme_input,
                provider=provider_code,
                api_base=api_base_input,
                api_key=api_key_input,
                model=model_input
            )
            st.session_state["expansion_res"] = expansion_res
            st.success("🎉 LLMによる検索キーワード・分類コードの拡張処理が完了しました！")

    if "expansion_res" in st.session_state:
        exp = st.session_state["expansion_res"]
        
        if exp.get("is_fallback"):
            st.warning(
                "⚠️ **【通知】LLMへの接続ができなかったため、フォールバック（ルールベース生成）を適用しました。**\n\n"
                f"・理由: `{exp.get('fallback_reason')}`\n\n"
                "💡 **ヒント**: Gemini API Key を設定するか、ローカルLLM（LM Studio等）を起動すると、"
                "より高度なNDC自動分類や異体字・旧字体の自動拡張機能が有効になります。"
            )
        else:
            st.success(f"✨ **{provider_choice} による検索キーワード・分類パラメータの高度拡張が適用されています。**")

        with st.expander("📋 生成された検索パラメータ設定 (JSON)", expanded=True):
            st.json(exp)

        queries = generate_sparql_queries(exp)
        st.subheader(f"🔍 生成されたSPARQLクエリパターン ({len(queries)} パターン)")

        limit_val = st.number_input("1バッチあたりの取得上限 (LIMIT):", min_value=50, max_value=1000, value=200, step=50)

        if st.button("🚀 Japan Search からメタデータを全自動取得・深層構築する", type="primary", use_container_width=True):
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
