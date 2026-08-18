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
from views.step2_type_view import render_step2_type_view
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
    "PATH_TYPE_RULES": f"{RULES_DIR}/type_rules.json",
    "PATH_TYPE_FILTERED": f"{DATA_DIR}/type_filtered.jsonl",
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

status_map = {
    "Step 1: LLMクエリ拡張およびJapan Searchメタデータ取得": PATHS["PATH_RAW_METADATA"],
    "Step 2-A: データ種別 (rdf:type) 分析・除外": PATHS["PATH_TYPE_FILTERED"],
    "Step 2-B: 主題 (schema:about) キーワード分析・判別": PATHS["PATH_ABOUT_FILTERED"],
    "Step 2-C: タイトル語彙・文字列パターン分析・除外": PATHS["PATH_NGRAM_FILTERED"],
    "Step 3: LLMセマンティック適合判定 (判定保留群の分類)": PATHS["PATH_LLM_JUDGMENTS"],
    "Step 4: 専門家による最終査読・手動オーバーライド": PATHS["PATH_VERIFIED_JSONL"],
    "Step 5: データエクスポート (統合検索ポータル出力)": PATHS["PATH_EXPORT_JSON"]
}

menu_options = [
    "Dashboard",
    "Step 1: LLMクエリ拡張およびJapan Searchメタデータ取得",
    "Step 2-A: データ種別 (rdf:type) 分析・除外",
    "Step 2-B: 主題 (schema:about) キーワード分析・判別",
    "Step 2-C: タイトル語彙・文字列パターン分析・除外",
    "Step 3: LLMセマンティック適合判定 (判定保留群の分類)",
    "Step 4: 専門家による最終査読・手動オーバーライド",
    "Step 5: データエクスポート (統合検索ポータル出力)"
]

def format_menu_label(opt):
    if opt == "Dashboard":
        return "📊 Dashboard"
    p = status_map.get(opt)
    st_mark = check_status(p) if p else "○"
    return f"{st_mark} {opt}"

choice = st.sidebar.radio("工程を選択:", menu_options, format_func=format_menu_label, key="main_menu_choice")

# 画面切り替え時に以前のDOM要素を100%確実に消去するための独立コンテナ
main_view_container = st.empty()

with main_view_container.container():
    if choice == "Dashboard":
        render_dashboard_view(PATHS)
    elif choice == "Step 1: LLMクエリ拡張およびJapan Searchメタデータ取得":
        render_step1_view(PATHS)
    elif choice == "Step 2-A: データ種別 (rdf:type) 分析・除外":
        render_step2_type_view(PATHS)
    elif choice == "Step 2-B: 主題 (schema:about) キーワード分析・判別":
        render_step2a_view(PATHS)
    elif choice == "Step 2-C: タイトル語彙・文字列パターン分析・除外":
        render_step2b_view(PATHS)
    elif choice == "Step 3: LLMセマンティック適合判定 (判定保留群の分類)":
        render_step2c_view(PATHS)
    elif choice == "Step 4: 専門家による最終査読・手動オーバーライド":
        render_step2d_view(PATHS)
    elif choice == "Step 5: データエクスポート (統合検索ポータル出力)":
        render_step3_view(PATHS)
