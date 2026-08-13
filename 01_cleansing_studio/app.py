# -*- coding: utf-8 -*-
"""
MetaClean Studio - 人文学文化資源メタデータ抽出・構造化システム
メインエントリーポイント ＆ ルーティング
"""

import os
import re
import streamlit as st

# コンポーネント ＆ スタイル
from components.styles import inject_custom_css
from components.file_utils import count_lines

# ビューモジュール
from views.dashboard_view import render_dashboard_view
from views.step1_fetch_view import render_step1_view
from views.step2a_about_view import render_step2a_view
from views.step2b_ngram_view import render_step2b_view
from views.step2c_llm_view import render_step2c_view
from views.step2d_review_view import render_step2d_view
from views.step3_export_view import render_step3_view

# Streamlit ページ初期化
st.set_page_config(layout="wide", page_title="MetaClean Studio | メタデータ精緻化システム", page_icon="📚")

# 全体CSSの注入
inject_custom_css()

# パス定数定義
STUDIO_DIR = "01_cleansing_studio"
DATA_DIR = "data"
VIEWER_DIR = "02_search_viewer"
RULES_DIR = f"{STUDIO_DIR}/rules"

PATHS = {
    "PATH_RAW_METADATA": f"{DATA_DIR}/raw_metadata.jsonl",
    "PATH_TARGET_URIS": f"{DATA_DIR}/target_uris.csv",
    "PATH_ABOUT_RULES": f"{RULES_DIR}/about_rules.json",
    "PATH_NGRAM_RULES": f"{RULES_DIR}/ngram_rules.json",
    "PATH_ABOUT_FILTERED": f"{DATA_DIR}/about_filtered.jsonl",
    "PATH_NGRAM_FILTERED": f"{DATA_DIR}/ngram_filtered.jsonl",
    "PATH_TARGET_FOR_LLM": f"{DATA_DIR}/target_for_llm.jsonl",
    "PATH_CONFIRMED_OK": f"{DATA_DIR}/confirmed_ok_rules.jsonl",
    "PATH_DISCARDED_RULES": f"{DATA_DIR}/discarded_rules.csv",
    "PATH_LLM_JUDGMENTS": f"{DATA_DIR}/llm_judgments.jsonl",
    "PATH_VERIFIED_JSONL": f"{DATA_DIR}/human_verified_cleaned.jsonl",
    "PATH_EXPORT_JSON": f"{VIEWER_DIR}/scores_data.json"
}

# サイドバーメニュー構築
st.sidebar.title("MetaClean Studio")
st.sidebar.caption("人文学文化資源 メタデータ精緻化システム")

def check_status(path):
    return "●" if os.path.exists(path) and os.path.getsize(path) > 0 else "○"

step1_st = check_status(PATHS["PATH_RAW_METADATA"])
step2a_st = check_status(PATHS["PATH_ABOUT_FILTERED"])
step2b_st = check_status(PATHS["PATH_NGRAM_FILTERED"])
step2c_st = check_status(PATHS["PATH_LLM_JUDGMENTS"])
step2d_st = check_status(PATHS["PATH_VERIFIED_JSONL"])
step3_st = check_status(PATHS["PATH_EXPORT_JSON"])

menu_options = [
    "Dashboard",
    f"{step1_st} Step 1: LLMクエリ拡張およびJapan Searchメタデータ取得",
    f"{step2a_st} Step 2-A: 主題 (schema:about) キーワード分析・判別",
    f"{step2b_st} Step 2-B: タイトル N-Gram (N=2〜9) パターン分析・除外",
    f"{step2c_st} Step 2-C: LLMセマンティック適合判定 (判定保留群の分類)",
    f"{step2d_st} Step 2-D: 専門家による最終査読・手動オーバーライド",
    f"{step3_st} Step 3: データエクスポート (統合検索ポータル出力)"
]

choice_raw = st.sidebar.radio("工程を選択:", menu_options)
choice = re.sub(r'^[●○]\s*', '', choice_raw)

# ビューのルーティング実行
if choice == "Dashboard":
    render_dashboard_view(PATHS)
elif choice == "Step 1: LLMクエリ拡張およびJapan Searchメタデータ取得":
    render_step1_view(PATHS)
elif choice == "Step 2-A: 主題 (schema:about) キーワード分析・判別":
    render_step2a_view(PATHS)
elif choice == "Step 2-B: タイトル N-Gram (N=2〜9) パターン分析・除外":
    render_step2b_view(PATHS)
elif choice == "Step 2-C: LLMセマンティック適合判定 (判定保留群の分類)":
    render_step2c_view(PATHS)
elif choice == "Step 2-D: 専門家による最終査読・手動オーバーライド":
    render_step2d_view(PATHS)
elif choice == "Step 3: データエクスポート (統合検索ポータル出力)":
    render_step3_view(PATHS)
