# -*- coding: utf-8 -*-
"""
MetaClean Studio - カスタムCSS ＆ スタイル定義モジュール
"""
import streamlit as st

def inject_custom_css():
    """全体デザイン拡張 ＆ 画面安定化CSSを注入"""
    st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700&family=Noto+Sans+JP:wght@400;500;700&display=swap');

    html, body, [class*="css"]  {
        font-family: 'Plus Jakarta Sans', 'Noto Sans JP', -apple-system, sans-serif;
    }

    div[data-testid="stAppViewBlockContainer"] {
        opacity: 1 !important;
        transition: none !important;
        padding-top: 1.2rem;
    }
    .element-container, .stButton, div[data-st-mode="running"] {
        opacity: 1 !important;
        transition: none !important;
    }
    [data-testid="stStatusWidget"] {
        visibility: hidden !important;
    }

    /* メトリックカード */
    div[data-testid="stMetric"] {
        background: linear-gradient(145deg, rgba(255,255,255,0.06), rgba(255,255,255,0.02));
        border: 1px solid rgba(128, 128, 128, 0.18);
        border-radius: 12px;
        padding: 14px 18px;
        box-shadow: 0 4px 12px rgba(0, 0, 0, 0.04);
    }

    /* サイドバータイトル */
    [data-testid="stSidebar"] {
        border-right: 1px solid rgba(128, 128, 128, 0.15);
    }

    /* ヒーローカードバナー */
    .hero-card {
        background: linear-gradient(135deg, #1e1b4b 0%, #312e81 50%, #0f172a 100%);
        color: #ffffff;
        border-radius: 16px;
        padding: 24px 30px;
        margin-bottom: 24px;
        box-shadow: 0 10px 25px -5px rgba(30, 27, 75, 0.3);
    }
    .hero-card h1 {
        color: #ffffff !important;
        font-size: 26px;
        font-weight: 700;
        margin: 0 0 8px 0;
    }
    .hero-card p {
        color: #c7d2fe;
        font-size: 14px;
        margin: 0;
        line-height: 1.6;
    }

    .sub-card {
        background: rgba(255, 255, 255, 0.03);
        border: 1px solid rgba(128, 128, 128, 0.15);
        border-radius: 12px;
        padding: 18px 22px;
        margin-bottom: 16px;
    }

    /* OK (緑) ＆ NG (赤) ＆ 未判定 ボタンの完全超ビジュアル色分けスタイル */
    div.stButton > button:has(div:contains("🟢")),
    div.stButton > button:has(div:contains("✅")),
    div.stButton > button:has(p:contains("🟢")),
    div.stButton > button:has(p:contains("✅")) {
        background-color: #064e3b !important;
        border: 1.5px solid #10b981 !important;
        color: #6ee7b7 !important;
        font-weight: 700 !important;
        box-shadow: 0 2px 6px rgba(16, 185, 129, 0.25) !important;
    }

    div.stButton > button:has(div:contains("🔴")),
    div.stButton > button:has(div:contains("🚫")),
    div.stButton > button:has(p:contains("🔴")),
    div.stButton > button:has(p:contains("🚫")) {
        background-color: #7f1d1d !important;
        border: 1.5px solid #ef4444 !important;
        color: #fca5a5 !important;
        font-weight: 700 !important;
        box-shadow: 0 2px 6px rgba(239, 68, 68, 0.25) !important;
    }

    div.stButton > button:has(div:contains("⚪")),
    div.stButton > button:has(p:contains("⚪")) {
        background-color: #1e293b !important;
        border: 1px solid #475569 !important;
        color: #94a3b8 !important;
    }
    </style>
    """, unsafe_allow_html=True)
