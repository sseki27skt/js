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

    st.write("---")
    # --- 全データリセットセクション ---
    st.subheader("⚠️ システム初期化・全作業リセット")
    
    with st.container(border=True):
        st.markdown("""
        <div style="background-color: rgba(255, 75, 75, 0.1); border-left: 5px solid #ff4b4b; padding: 12px 16px; border-radius: 4px; margin-bottom: 12px;">
            <h4 style="color: #ff4b4b; margin: 0 0 6px 0;">【警告】すべての作業データおよび設定ルールが完全に消去されます</h4>
            <p style="margin: 0; font-size: 0.92rem; color: #dcdcdc; line-height: 1.5;">
                この操作を実行すると、Japan Searchから収集した<b>生メタデータ（raw_metadata.jsonl）</b>、
                Step 2の<b>全フィルタリング結果（About/N-Gram/LLM判定結果）</b>、
                構築された<b>除外・保持ルール設定（JSON）</b>、
                および<b>専門家査読データ</b>を含むすべてのファイルが<b>物理的に完全削除</b>されます。<br>
                この操作は取り消すことができません。
            </p>
        </div>
        """, unsafe_allow_html=True)

        confirm_reset = st.checkbox(
            "取得した生メタデータ、設定ルール、判定ログを含むすべてのデータを完全に削除し、ゼロからやり直すことを確認・同意しました",
            key="chk_confirm_full_reset"
        )

        c_rst1, c_rst2 = st.columns([1, 3])
        with c_rst1:
            if st.button("🔥 すべてをリセットしてゼロからやり直す", type="primary", disabled=not confirm_reset, use_container_width=True):
                import os
                import time

                # 削除対象ファイルリスト
                delete_targets = list(paths.values()) + [
                    "data/discarded_about.csv",
                    "data/discarded_ngram.csv",
                    "data/discarded_suffix_filtered.csv",
                    "data/suffix_filtered.jsonl",
                    "data/tmp_llm_grey_judgments.jsonl",
                    "data/about_keywords_ranking.csv",
                    "data/vocab_ranking_scores.csv"
                ]

                deleted_count = 0
                for file_path in set(delete_targets):
                    if os.path.exists(file_path):
                        try:
                            os.remove(file_path)
                            deleted_count += 1
                        except Exception as e:
                            st.warning(f"削除スキップ: {file_path} ({e})")

                # キャッシュおよびセッション状態のクリア
                st.cache_data.clear()
                st.session_state.clear()

                st.success(f"初期化完了: 合計 {deleted_count} 個のデータファイルとキャッシュを完全消去しました。システムを初期状態へ再起動します...")
                time.sleep(1.2)
                st.rerun()

        with c_rst2:
            st.caption("※ チェックボックスにチェックを入れると初期化実行ボタンが有効化されます。")

