# -*- coding: utf-8 -*-
"""
MetaClean Studio - 汎用ピルボード (Pill Board) ＆ 仮判定操作UIコンポーネント
"""

import math
import streamlit as st
from components.file_utils import make_google_link

def render_pill_board(
    items: list, 
    active_samples_map: dict, 
    current_ng: set, 
    current_ok: set, 
    draft_dict: dict, 
    click_action_mode: str,
    page_session_key: str,
    parent_rule_func=None,
    items_per_page: int = 36
):
    """
    キーワード/フレーズのピル（Pill）一覧をインタラクティブかつ爆速描画する汎用コンポーネント
    
    :param items: (word, total_count) または (word, total_count, raw_samples) のリスト
    :param active_samples_map: word -> active_samples リストの辞書
    :param current_ng: 確定済みNGセット
    :param current_ok: 確定済みOKセット
    :param draft_dict: 仮選択中ステータス辞書
    :param click_action_mode: 現在の判定モード ("🚫 NGに判定", "✅ OKに判定", "🔄 未判定に戻す")
    :param page_session_key: ページネーション用のセッションキー
    :param parent_rule_func: (word) -> (parent_type, parent_word) を返す関数 (オプション)
    :param items_per_page: 1ページあたりの描画アイテム数
    """
    total_items = len(items)
    if total_items == 0:
        st.info("条件に一致する判定対象キーワードはありません。")
        return

    total_pages = math.ceil(total_items / items_per_page)
    
    if page_session_key not in st.session_state:
        st.session_state[page_session_key] = 1
    cur_p = max(1, min(total_pages, int(st.session_state.get(page_session_key, 1))))
    st.session_state[page_session_key] = cur_p

    # ページネーションバー
    c_p1, c_p2, c_p3 = st.columns([1, 2, 1])
    with c_p1:
        if st.button("◀ 前へ", disabled=(cur_p <= 1), key=f"btn_prev_{page_session_key}", use_container_width=True):
            st.session_state[page_session_key] = cur_p - 1
            st.rerun(scope="fragment")
    with c_p2:
        st.markdown(
            f"<div style='text-align: center; padding-top: 6px;'><b>全 {total_items:,} 件中 "
            f"{(cur_p-1)*items_per_page+1}〜{min(total_items, cur_p*items_per_page)}件を表示 "
            f"( {cur_p} / {total_pages} ページ )</b></div>", 
            unsafe_allow_html=True
        )
    with c_p3:
        if st.button("次へ ▶", disabled=(cur_p >= total_pages), key=f"btn_next_{page_session_key}", use_container_width=True):
            st.session_state[page_session_key] = cur_p + 1
            st.rerun(scope="fragment")

    page_items = items[(cur_p-1)*items_per_page : cur_p*items_per_page]

    # ボードコンテナ
    board_container = st.container(height=520)
    with board_container:
        grid_cols = st.columns(3)
        for idx, item in enumerate(page_items):
            col = grid_cols[idx % 3]
            
            w = item[0]
            cnt = item[1]
            raw_samples = item[2] if len(item) > 2 else []

            parent_type, parent_word = (None, None)
            if parent_rule_func:
                parent_type, parent_word = parent_rule_func(w)

            active_info = active_samples_map.get(w, {})
            if isinstance(active_info, dict):
                eff_c = active_info.get("eff_cnt", 0)
                display_samples = active_info.get("samples", [])
            elif isinstance(active_info, list):
                eff_c = len(active_info)
                display_samples = active_info
            else:
                eff_c = cnt
                display_samples = raw_samples

            cnt_str = f"({cnt}件)" if eff_c == cnt else f"(未判定 {eff_c}件 / 全{cnt}件)"

            sample_lines = [f"• {t}" for t in display_samples[:20]]
            sample_header = f"【『{w}』の未判定資料サンプル (未判定 {eff_c}例中 先頭{len(sample_lines)}件表示)】:\n" if display_samples else f"【『{w}』の件数: {cnt_str}】\n"
            tooltip_txt = sample_header + "\n".join(sample_lines)

            # ドラフト ＆ 既存ルールのステータス判定
            draft_status = draft_dict.get(w)
            if draft_status == "NG":
                is_ng, is_ok = True, False
                d_tag = " [仮NG]"
            elif draft_status == "OK":
                is_ng, is_ok = False, True
                d_tag = " [仮OK]"
            elif draft_status == "RESET":
                is_ng, is_ok = False, False
                d_tag = " [仮未判定]"
            else:
                is_ng = w in current_ng
                is_ok = w in current_ok
                d_tag = ""

            if is_ng:
                btn_label = f"🚫 {w} {cnt_str}{d_tag}"
            elif is_ok:
                btn_label = f"✅ {w} {cnt_str}{d_tag}"
            elif parent_type == "NG":
                btn_label = f"🚫 {w} [親:{parent_word}] {cnt_str}{d_tag}"
            elif parent_type == "OK":
                btn_label = f"✅ {w} [親:{parent_word}] {cnt_str}{d_tag}"
            else:
                btn_label = f"❓ {w} {cnt_str}{d_tag}"

            c_btn, c_pop = col.columns([6, 1])
            with c_btn:
                if st.button(btn_label, key=f"btn_pills_{page_session_key}_{w}_{idx}_{cur_p}", help=tooltip_txt, use_container_width=True):
                    if click_action_mode == "🚫 NGに判定":
                        draft_dict[w] = "NG"
                    elif click_action_mode == "✅ OKに判定":
                        draft_dict[w] = "OK"
                    elif click_action_mode == "🔄 未判定に戻す":
                        draft_dict[w] = "RESET"
                    st.rerun(scope="fragment")

            with c_pop:
                with st.popover("🔍", help=f"『{w}』の検索・詳細"):
                    st.markdown(f"### 🔍 『{w}』")
                    st.markdown(f"- **Google検索**: {make_google_link(w)}")
                    st.markdown(f"- **件数内訳**: 未判定 {eff_c} 件 / 全 {cnt} 件")
                    if parent_type:
                        st.info(f"親ルール継承: **{parent_type}** (親パターン: 『{parent_word}』)")
                    st.write("---")
                    st.caption(f"📄 **未判定の出現資料タイトル一覧 (最新 {len(display_samples)} 件)**:")
                    with st.container(height=280):
                        for s_title in display_samples:
                            st.markdown(f"- {s_title}")
