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
        <h1>✨ MetaClean Studio</h1>
        <p>文化資源メタデータの自動抽出・多層ルールフィルタリング・LLMセマンティック分類・人間査読を統合した高性能クレンジングポータルです。</p>
    </div>
    """, unsafe_allow_html=True)

    st.subheader("📊 パイプライン全体進捗ダッシュボード")

    cols = st.columns(4)
    with cols[0]:
        st.info("🌐 Phase 1: データ収集")
        st.metric("収集Rawメタデータ", f"{count_lines(paths['PATH_RAW_METADATA']):,} 件")

    with cols[1]:
        st.warning("⚡ Phase 2: ルールベース")
        st.metric("About フィルタ通過", f"{count_lines(paths['PATH_ABOUT_FILTERED']):,} 件")
        st.metric("N-Gram フィルタ通過", f"{count_lines(paths['PATH_NGRAM_FILTERED']):,} 件")

    with cols[2]:
        st.success("🤖 Phase 3: LLM & 査読")
        st.metric("LLM判定データ", f"{count_lines(paths['PATH_LLM_JUDGMENTS']):,} 件")
        st.metric("人間査読・確定データ", f"{count_lines(paths['PATH_VERIFIED_JSONL']):,} 件")

    with cols[3]:
        st.error("🚀 Phase 4: 成果物")
        st.metric("ポータル出力データ", f"{count_lines(paths['PATH_EXPORT_JSON']):,} 件")

    st.write("---")
    st.subheader("💡 ワークフロークイックアクセス")
    st.markdown("サイドバーのメニューから、目的のパイプライン工程を選択して直接作業を開始できます。")
