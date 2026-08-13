# -*- coding: utf-8 -*-
"""
MetaClean Studio - Dashboard ビュー
"""
import streamlit as st
from components.file_utils import count_lines

def render_dashboard_view(paths: dict):
    """ダッシュボード画面を描画"""
    st.markdown("""
    <div class="hero-card">
        <h1>MetaClean Studio</h1>
        <p>人文学文化資源メタデータの網羅的抽出・多層ルールフィルタリング・LLMセマンティック適合判定・専門家査読を統合した精緻化システムです。</p>
    </div>
    """, unsafe_allow_html=True)

    st.subheader("パイプライン全体進捗ダッシュボード")

    cols = st.columns(4)
    with cols[0]:
        st.info("Phase 1: メタデータ取得")
        st.metric("母集団 Raw メタデータ", f"{count_lines(paths['PATH_RAW_METADATA']):,} 件")

    with cols[1]:
        st.warning("Phase 2: 高速ルールフィルタ")
        st.metric("Aboutキーワード判別通過", f"{count_lines(paths['PATH_ABOUT_FILTERED']):,} 件")
        st.metric("N-Gramパターン除外通過", f"{count_lines(paths['PATH_NGRAM_FILTERED']):,} 件")

    with cols[2]:
        st.success("Phase 3: LLM判定・専門家査読")
        st.metric("LLMセマンティック判定数", f"{count_lines(paths['PATH_LLM_JUDGMENTS']):,} 件")
        st.metric("専門家査読・最終確定数", f"{count_lines(paths['PATH_VERIFIED_JSONL']):,} 件")

    with cols[3]:
        st.error("Phase 4: 出力データ構造化")
        st.metric("統合検索用出力データ", f"{count_lines(paths['PATH_EXPORT_JSON']):,} 件")

    st.write("---")
    st.subheader("ワークフロー概要")
    st.markdown("左側のサイドバーメニューより各分析・精緻化工程を選択し、順次処理を実行してください。")
