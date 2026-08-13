# -*- coding: utf-8 -*-
"""
MetaClean Studio - Step 2-A: Aboutキーワード仕分けビュー
"""
import json
import math
import os
import re
from collections import defaultdict
import streamlit as st

from components.file_utils import safe_save_json
from components.pill_board import render_pill_board
from modules.rule_filter import (
    run_about_filter,
    suggest_ng_keywords_with_llm,
    extract_about_keywords_from_jsonl,
    extract_about_values
)

try:
    import streamlit_hotkeys as hotkeys
except Exception:
    hotkeys = None

def cluster_about_keywords(about_ranking):
    """Aboutキーワードを階層構造および2-gram / 共通接尾辞・部分文字列でクラスタリング"""
    if not about_ranking:
        return []
    
    prefix_groups = defaultdict(list)
    unassigned = []
    
    for kw, count in about_ranking:
        m = re.match(r'^(.*?)(?:[--_/\s:･]|\s+)(.+)$', kw)
        if m:
            parent = m.group(1).strip()
            if "--" in kw:
                parts = kw.split("--")
                parent = "--".join(parts[:-1]) if len(parts) > 1 else parts[0]
            prefix_groups[parent].append((kw, count))
        else:
            unassigned.append((kw, count))
            
    clusters = []
    cluster_idx = 0
    
    for pkey, items in prefix_groups.items():
        if len(items) >= 2:
            items_sorted = sorted(items, key=lambda x: x[1], reverse=True)
            total_cnt = sum(c for k, c in items_sorted)
            clusters.append({
                "cluster_id": f"cl_p_{cluster_idx}",
                "name": f"階層: {pkey}",
                "keywords": [k for k, c in items_sorted],
                "total_count": total_cnt
            })
            cluster_idx += 1
        else:
            unassigned.extend(items)
            
    def get_bigrams(s):
        s_clean = re.sub(r'[\W_]+', '', s.lower())
        if len(s_clean) <= 1:
            return set([s_clean])
        return set(s_clean[i:i+2] for i in range(len(s_clean)-1))
        
    visited = set()
    for i, (kw1, cnt1) in enumerate(unassigned):
        if kw1 in visited:
            continue
        group = [(kw1, cnt1)]
        visited.add(kw1)
        bg1 = get_bigrams(kw1)
        
        for j in range(i + 1, len(unassigned)):
            kw2, cnt2 = unassigned[j]
            if kw2 in visited:
                continue
            bg2 = get_bigrams(kw2)
            
            is_sub = (len(kw1) >= 2 and kw1 in kw2) or (len(kw2) >= 2 and kw2 in kw1)
            is_same_suffix = (len(kw1) >= 2 and len(kw2) >= 2 and (kw1[-2:] == kw2[-2:] or kw1[:2] == kw2[:2]))
            
            union_len = len(bg1 | bg2)
            jaccard = len(bg1 & bg2) / union_len if union_len > 0 else 0
            
            if is_sub or jaccard >= 0.35 or (is_same_suffix and jaccard >= 0.25):
                group.append((kw2, cnt2))
                visited.add(kw2)
                
        if len(group) >= 2:
            group_sorted = sorted(group, key=lambda x: x[1], reverse=True)
            rep_name = group_sorted[0][0]
            total_cnt = sum(c for k, c in group_sorted)
            clusters.append({
                "cluster_id": f"cl_j_{cluster_idx}",
                "name": f"関連: {rep_name} グループ",
                "keywords": [k for k, c in group_sorted],
                "total_count": total_cnt
            })
            cluster_idx += 1
        else:
            clusters.append({
                "cluster_id": f"cl_s_{cluster_idx}",
                "name": f"単一: {kw1}",
                "keywords": [kw1],
                "total_count": cnt1
            })
            cluster_idx += 1
            
    clusters.sort(key=lambda x: x["total_count"], reverse=True)
    return clusters


def render_step2a_view(paths: dict):
    """Step 2-A 画面の描画"""
    st.title("Step 2-A: Schema:About キーワード仕分け ＆ LLMコンテキストサジェスト")
    st.markdown("収集データ内の `schema:about` キーワード一覧から、**除外すべきノイズパターン (NG)** および **保持したいパターン (OK)** を仕分けします。")

    raw_metadata_path = paths['PATH_RAW_METADATA']
    about_rules_path = paths['PATH_ABOUT_RULES']
    about_filtered_path = paths['PATH_ABOUT_FILTERED']

    if not os.path.exists(raw_metadata_path):
        st.warning("先に Step 1 で生メタデータ (raw_metadata.jsonl) を取得してください。")
        st.stop()

    os.makedirs(os.path.dirname(about_rules_path), exist_ok=True)
    
    @st.cache_data(show_spinner=False)
    def load_raw_item_features(path):
        about_ranking = extract_about_keywords_from_jsonl(path)
        records_data = []
        kw_to_doc_indices = defaultdict(list)
        if os.path.exists(path):
            with open(path, 'r', encoding='utf-8', errors='ignore') as f:
                idx = 0
                for line in f:
                    if not line.strip(): continue
                    try:
                        item = json.loads(line)
                        about_list = item.get("schema:about", [])
                        kw_set = set(extract_about_values(about_list))

                        label_val = item.get("rdfs:label", item.get("schema:name", ""))
                        title_str = str(label_val[0]) if isinstance(label_val, list) and label_val else str(label_val)

                        records_data.append({
                            "id": item.get("@id", ""),
                            "title": title_str,
                            "about_set": kw_set
                        })
                        for kw in kw_set:
                            kw_to_doc_indices[kw].append(idx)
                        idx += 1
                    except Exception:
                        continue
        return about_ranking, records_data, kw_to_doc_indices

    about_ranking, raw_records, kw_to_doc_indices = load_raw_item_features(raw_metadata_path)

    if not about_ranking:
        st.info("データ内に schema:about キーワードが見つかりませんでした。")
        st.stop()
    
    if "edited_noise" not in st.session_state:
        rules = {}
        if os.path.exists(about_rules_path):
            with open(about_rules_path, 'r', encoding='utf-8') as f:
                rules = json.load(f)
        st.session_state["edited_noise"] = set([k for k, v in rules.items() if v == "NG"])
        st.session_state["edited_strong"] = set([k for k, v in rules.items() if v == "OK"])

    current_ng = st.session_state["edited_noise"]
    current_ok = st.session_state["edited_strong"]

    if "checked_words" not in st.session_state:
        st.session_state["checked_words"] = set()
    if "chk_view_ver" not in st.session_state:
        st.session_state["chk_view_ver"] = 0

    checked_words = st.session_state["checked_words"]

    total_about_types = len(about_ranking)
    all_kw_set = set([k for k, c in about_ranking])
    ng_classified_count = len(all_kw_set & current_ng)
    ok_classified_count = len(all_kw_set & current_ok)
    unclassified_count = total_about_types - ng_classified_count - ok_classified_count

    st.subheader("📊 Aboutキーワード分類サマリー")
    m_col1, m_col2, m_col3, m_col4 = st.columns(4)
    with m_col1:
        st.metric("トータル About種類数", f"{total_about_types:,} 種類")
    with m_col2:
        st.metric("🚫 NG (除外) 分類数", f"{ng_classified_count:,} 種類", delta=f"{ng_classified_count/max(1,total_about_types):.1%}", delta_color="inverse")
    with m_col3:
        st.metric("✅ OK (保持) 分類数", f"{ok_classified_count:,} 種類", delta=f"{ok_classified_count/max(1,total_about_types):.1%}")
    with m_col4:
        st.metric("❓ 未判定キーワード数", f"{unclassified_count:,} 種類")

    with st.expander(f"📋 現在の About NG / OK 登録リストを確認・管理する (🚫 NG: {len(current_ng)} 件 / ✅ OK: {len(current_ok)} 件)", expanded=False):
        c_manage_ng, c_manage_ok = st.columns(2)
        with c_manage_ng:
            st.markdown(f"### 🚫 除外(NG) リスト ({len(current_ng)} 件)")
            if current_ng:
                ng_list_sorted = sorted(list(current_ng))
                try:
                    selected_ab_ng_pills = st.pills("反転選択して削除する単語をクリック:", options=ng_list_sorted, selection_mode="multi", key="pills_about_ng")
                except AttributeError:
                    selected_ab_ng_pills = st.multiselect("削除する単語を選択:", options=ng_list_sorted, key="ms_about_ng_fallback")

                if st.button("🗑️ 選択した単語を NG リストから登録解除（削除）", key="btn_del_ab_ng_pills", type="primary", use_container_width=True):
                    if selected_ab_ng_pills:
                        current_ng.difference_update(selected_ab_ng_pills)
                        st.session_state["chk_view_ver"] += 1
                        st.success(f"🎉 {len(selected_ab_ng_pills)} 件の単語を NG リストから削除しました！")
                        st.rerun()
                    else:
                        st.warning("解除する単語が選択されていません。")
            else:
                st.info("NG リストは現在空です。")

        with c_manage_ok:
            st.markdown(f"### ✅ 保持(OK) リスト ({len(current_ok)} 件)")
            if current_ok:
                ok_list_sorted = sorted(list(current_ok))
                try:
                    selected_ab_ok_pills = st.pills("反転選択して削除する単語をクリック:", options=ok_list_sorted, selection_mode="multi", key="pills_about_ok")
                except AttributeError:
                    selected_ab_ok_pills = st.multiselect("削除する単語を選択:", options=ok_list_sorted, key="ms_about_ok_fallback")

                if st.button("🗑️ 選択した単語を OK リストから登録解除（削除）", key="btn_del_ab_ok_pills", type="primary", use_container_width=True):
                    if selected_ab_ok_pills:
                        current_ok.difference_update(selected_ab_ok_pills)
                        st.session_state["chk_view_ver"] += 1
                        st.success(f"🎉 {len(selected_ab_ok_pills)} 件の単語を OK リストから削除しました！")
                        st.rerun()
                    else:
                        st.warning("解除する単語が選択されていません。")
            else:
                st.info("OK リストは現在空です。")

    ng_doc_indices = set()
    for ng_kw in current_ng:
        ng_doc_indices.update(kw_to_doc_indices.get(ng_kw, []))

    active_doc_indices = set(range(len(raw_records))) - ng_doc_indices

    st.write("---")

    @st.cache_data(show_spinner=False)
    def get_cached_about_clusters(about_ranking_list):
        return cluster_about_keywords(about_ranking_list)

    about_clusters = get_cached_about_clusters(about_ranking)

    tab_cluster, tab_single, tab_llm = st.tabs([
        "🧩 クラスタ一括仕分け (推奨)",
        "🔤 単体キーワード仕分けボード",
        "💡 LLM全体ノイズ提案"
    ])

    with tab_cluster:
        st.markdown("機械的に類似性を抽出したキーワードグループごとに **仮選択 (OK/NG/未判定)** を行い、上部の **『🚀 一括確定』** ボタンでまとめて適用できます。")

        if "draft_about_changes" not in st.session_state:
            st.session_state["draft_about_changes"] = {}
        draft_ab = st.session_state["draft_about_changes"]

        def get_eff_status(kw):
            if kw in draft_ab:
                v = draft_ab[kw]
                return "OK" if v == "OK" else ("NG" if v == "NG" else "UN")
            if kw in current_ok:
                return "OK"
            if kw in current_ng:
                return "NG"
            return "UN"

        @st.fragment
        def render_cluster_board():
            c_cl_hdr1, c_cl_hdr2 = st.columns([3, 2])
            with c_cl_hdr1:
                draft_count = len(draft_ab)
                if draft_count > 0:
                    st.warning(f"⚡ **現在 {draft_count} 件のキーワードが仮選択中（未適用）です。**")
                else:
                    st.caption("下部のクラスタで OK / NG を仮選択し、準備ができたら『一括確定』を押してください。")
            with c_cl_hdr2:
                btn_apply_label = f"🚀 仮判定 ({draft_count} 件) を一括確定して適用" if draft_count > 0 else "🚀 判定を一括確定して適用"
                if st.button(btn_apply_label, type="primary" if draft_count > 0 else "secondary", use_container_width=True, key="btn_apply_cluster_draft"):
                    if draft_ab:
                        for kw, status in draft_ab.items():
                            if status == "NG":
                                current_ng.add(kw)
                                current_ok.discard(kw)
                            elif status == "OK":
                                current_ok.add(kw)
                                current_ng.discard(kw)
                            elif status == "RESET":
                                current_ng.discard(kw)
                                current_ok.discard(kw)
                        draft_ab.clear()
                        
                        save_dict = {}
                        for k in current_ng: save_dict[k] = "NG"
                        for k in current_ok: save_dict[k] = "OK"
                        safe_save_json(save_dict, about_rules_path)

                        st.session_state["chk_view_ver"] += 1
                        st.success("🎉 クラスタ仮判定を about_rules.json へ保存・適用しました！")
                        st.rerun()
                    else:
                        st.info("現在仮選択中のキーワードはありません。")

            st.write("---")

            ctrl_col1, ctrl_col2, ctrl_col3 = st.columns([3, 2, 2])
            with ctrl_col1:
                hide_fully_classified = st.checkbox("全語句が判定済みのクラスタを非表示にする", value=False, key="chk_hide_classified_clusters")
            with ctrl_col2:
                sort_cluster_by = st.selectbox("ソート順:", ["合計データ件数順", "所属キーワード数順"], key="sb_cluster_sort")
            with ctrl_col3:
                clusters_per_page = st.number_input("1ページ表示数 (軽量化)", min_value=5, max_value=100, value=10, step=5, key="num_clusters_per_page")

            display_clusters = []
            for c in about_clusters:
                kws = c["keywords"]
                ng_c = sum(1 for k in kws if k in current_ng)
                ok_c = sum(1 for k in kws if k in current_ok)
                un_c = len(kws) - ng_c - ok_c

                if hide_fully_classified and un_c == 0:
                    continue

                display_clusters.append({
                    **c,
                    "ng_count": ng_c,
                    "ok_count": ok_c,
                    "un_count": un_c
                })

            if sort_cluster_by == "所属キーワード数順":
                display_clusters.sort(key=lambda x: len(x["keywords"]), reverse=True)
            else:
                display_clusters.sort(key=lambda x: x["total_count"], reverse=True)

            total_display_clusters = len(display_clusters)

            if total_display_clusters == 0:
                st.success("🎉 現在表示条件に一致する未判定のクラスタはありません！")
                return

            safe_per_page = max(1, int(clusters_per_page))
            total_pages = math.ceil(total_display_clusters / safe_per_page)
            if "cluster_page_idx" not in st.session_state:
                st.session_state["cluster_page_idx"] = 1

            current_page = max(1, min(total_pages, int(st.session_state.get("cluster_page_idx", 1))))
            st.session_state["cluster_page_idx"] = current_page

            p_col1, p_col2, p_col3 = st.columns([1, 2, 1])
            with p_col1:
                if st.button("◀ 前のページ", disabled=(current_page <= 1), key="btn_prev_cluster_page", use_container_width=True):
                    st.session_state["cluster_page_idx"] = max(1, current_page - 1)
                    st.rerun(scope="fragment")
            with p_col2:
                st.markdown(f"<div style='text-align: center; padding-top: 6px;'><b>全 {total_display_clusters} クラスタ中 {current_page} / {total_pages} ページを表示</b></div>", unsafe_allow_html=True)
            with p_col3:
                if st.button("次のページ ▶", disabled=(current_page >= total_pages), key="btn_next_cluster_page", use_container_width=True):
                    st.session_state["cluster_page_idx"] = min(total_pages, current_page + 1)
                    st.rerun(scope="fragment")

            start_idx = (current_page - 1) * safe_per_page
            end_idx = start_idx + safe_per_page
            page_clusters = display_clusters[start_idx:end_idx]

            st.write("---")

            for idx, c in enumerate(page_clusters):
                cid = c["cluster_id"]
                kws = c["keywords"]
                un_c = c["un_count"]
                ok_c = c["ok_count"]
                ng_c = c["ng_count"]

                if ng_c > 0 and ok_c == 0 and un_c == 0:
                    status_badge = "🔴 全除外 (NG)"
                elif ok_c > 0 and ng_c == 0 and un_c == 0:
                    status_badge = "🟢 全保持 (OK)"
                elif ok_c > 0 or ng_c > 0:
                    status_badge = f"🌗 混合 (OK:{ok_c} / NG:{ng_c} / 未:{un_c})"
                else:
                    status_badge = f"❓ 未判定 (全{un_c}件)"

                kw_preview = ", ".join(kws[:5]) + ("..." if len(kws) > 5 else "")
                expander_title = f"📦 {c['name']} ➔ [{status_badge}] （含む語句: {kw_preview} [{len(kws)}種類] / 合計データ: {c['total_count']:,} 件）"

                with st.expander(expander_title, expanded=(un_c > 0)):
                    b_col1, b_col2, b_col3 = st.columns(3)
                    with b_col1:
                        if st.button(f"🟢 一括 OK (仮選択) [{len(kws)}件]", key=f"btn_cl_ok_{cid}", type="secondary", use_container_width=True):
                            for k in kws:
                                draft_ab[k] = "OK"
                            st.rerun(scope="fragment")
                    with b_col2:
                        if st.button(f"🔴 一括 NG (仮選択) [{len(kws)}件]", key=f"btn_cl_ng_{cid}", type="primary", use_container_width=True):
                            for k in kws:
                                draft_ab[k] = "NG"
                            st.rerun(scope="fragment")
                    with b_col3:
                        if st.button(f"⚪ 一括 未判定リセット", key=f"btn_cl_reset_{cid}", use_container_width=True):
                            for k in kws:
                                draft_ab[k] = "RESET"
                            st.rerun(scope="fragment")

                    st.caption("👇 個別トグル切替 (クリックすると 🟢 OK ⇄ 🔴 NG が即座にトグル反転します):")
                    cl_cols = st.columns(4)
                    for idx_k, kw in enumerate(kws):
                        col_k = cl_cols[idx_k % 4]
                        st_val = get_eff_status(kw)
                        
                        if st_val == "OK":
                            lbl = f"🟢 [OK] {kw}"
                        elif st_val == "NG":
                            lbl = f"🔴 [NG] {kw}"
                        else:
                            lbl = f"⚪ [未判定] {kw}"

                        def make_toggle_func(target_kw, current_st):
                            def toggle_status():
                                if current_st == "OK":
                                    draft_ab[target_kw] = "NG"
                                else:
                                    draft_ab[target_kw] = "OK"
                            return toggle_status

                        col_k.button(
                            lbl, 
                            key=f"tgl_kw_{cid}_{kw}", 
                            on_click=make_toggle_func(kw, st_val), 
                            use_container_width=True
                        )

        render_cluster_board()

    with tab_single:
        col_opt1, col_opt2 = st.columns([3, 2])
        with col_opt1:
            view_filter_mode = st.radio(
                "👁️ 表示オプション:", 
                options=["🌐 すべて表示", "❓ 未判定のみ", "🚫 NGのみ", "✅ OKのみ"], 
                horizontal=True,
                key="view_filter_about_mode"
            )
            is_unclassified_mode = (view_filter_mode == "❓ 未判定のみ")
            hide_zero_about = st.checkbox(
                "🙈 残存未判定件数が 0 件 (影響なし) のキーワードを非表示にする", 
                value=True, 
                disabled=not is_unclassified_mode,
                key="chk_hide_zero_about"
            )
        with col_opt2:
            search_query = st.text_input("🔍 キーワード検索:", placeholder="例: 演劇 -能", key="q_about_pills")

        if "click_action_about_mode" not in st.session_state:
            st.session_state["click_action_about_mode"] = "🚫 NGに判定"

        st.caption("⚡ 判定モード切替 (キーボードショートカット: Q / W / E キー):")
        c_m1, c_m2, c_m3 = st.columns(3)
        
        btn1_type = "primary" if st.session_state["click_action_about_mode"] == "🚫 NGに判定" else "secondary"
        btn2_type = "primary" if st.session_state["click_action_about_mode"] == "✅ OKに判定" else "secondary"
        btn3_type = "primary" if st.session_state["click_action_about_mode"] == "🔄 未判定に戻す" else "secondary"

        b1 = c_m1.button("🔴 【 Q 】 🚫 NG判定モード", key="btn_shortcut_ab_q", type=btn1_type, use_container_width=True)
        b2 = c_m2.button("🟢 【 W 】 ✅ OK判定モード", key="btn_shortcut_ab_w", type=btn2_type, use_container_width=True)
        b3 = c_m3.button("🔵 【 E 】 🔄 未判定リセット", key="btn_shortcut_ab_e", type=btn3_type, use_container_width=True)

        if hotkeys:
            if hotkeys.pressed("mode_ng"):
                st.session_state["click_action_about_mode"] = "🚫 NGに判定"
                st.rerun()
            elif hotkeys.pressed("mode_ok"):
                st.session_state["click_action_about_mode"] = "✅ OKに判定"
                st.rerun()
            elif hotkeys.pressed("mode_reset"):
                st.session_state["click_action_about_mode"] = "🔄 未判定に戻す"
                st.rerun()

        if b1:
            st.session_state["click_action_about_mode"] = "🚫 NGに判定"
            st.rerun()
        if b2:
            st.session_state["click_action_about_mode"] = "✅ OKに判定"
            st.rerun()
        if b3:
            st.session_state["click_action_about_mode"] = "🔄 未判定に戻す"
            st.rerun()

        click_action_mode = st.session_state["click_action_about_mode"]

        if click_action_mode == "🚫 NGに判定":
            st.error("🎯 **【現在のモード: 🚫 NG (除外) 登録モード】** (キーボード: `Q` キー)")
        elif click_action_mode == "✅ OKに判定":
            st.success("🎯 **【現在のモード: ✅ OK (保持) 登録モード】** (キーボード: `W` キー)")
        elif click_action_mode == "🔄 未判定に戻す":
            st.info("🎯 **【現在のモード: 🔄 未判定リセットモード】** (キーボード: `E` キー)")

        filtered_ranking = about_ranking
        if view_filter_mode == "❓ 未判定のみ":
            filtered_ranking = [(k, c) for k, c in filtered_ranking if k not in current_ng and k not in current_ok]
        elif view_filter_mode == "🚫 NGのみ":
            filtered_ranking = [(k, c) for k, c in filtered_ranking if k in current_ng]
        elif view_filter_mode == "✅ OKのみ":
            filtered_ranking = [(k, c) for k, c in filtered_ranking if k in current_ok]

        if search_query:
            parts = [p.strip() for p in re.split(r'\s+', search_query.replace('　', ' ')) if p.strip()]
            inc_words = [p.lower() for p in parts if not p.startswith('-')]
            exc_words = [p[1:].lower() for p in parts if p.startswith('-') and len(p) > 1]
            
            res_list = []
            for kw, cnt in filtered_ranking:
                kw_l = kw.lower()
                if all(i in kw_l for i in inc_words) and not any(e in kw_l for e in exc_words):
                    res_list.append((kw, cnt))
            filtered_ranking = res_list

        active_samples_info = {}
        for kw, cnt in filtered_ranking:
            doc_idx_list = kw_to_doc_indices.get(kw, [])
            act_indices = [idx for idx in doc_idx_list if idx in active_doc_indices]
            active_samples_info[kw] = {
                "eff_cnt": len(act_indices),
                "samples": [raw_records[i]["title"] for i in act_indices[:30]]
            }

        if is_unclassified_mode and hide_zero_about:
            filtered_ranking = [
                (kw, cnt) for kw, cnt in filtered_ranking 
                if active_samples_info.get(kw, {}).get("eff_cnt", 0) > 0 or kw in current_ng or kw in current_ok
            ]

        if "draft_about_changes" not in st.session_state:
            st.session_state["draft_about_changes"] = {}
        draft_ab = st.session_state["draft_about_changes"]

        # 汎用ピルボードコンポーネント呼出
        render_pill_board(
            items=filtered_ranking,
            active_samples_map=active_samples_info,
            current_ng=current_ng,
            current_ok=current_ok,
            draft_dict=draft_ab,
            click_action_mode=click_action_mode,
            page_session_key="about_single_page"
        )

        c_hdr1, c_hdr2 = st.columns([3, 2])
        with c_hdr1:
            st.markdown(f"判定対象キーワード (該当: **{len(filtered_ranking)}** 件 | **クリックで仮選択 ➔『一括確定』ボタンで確定**)")
        with c_hdr2:
            draft_count = len(draft_ab)
            btn_apply_label = f"🚀 仮判定 ({draft_count} 件) を一括確定して適用" if draft_count > 0 else "🚀 判定を一括確定して適用"
            if st.button(btn_apply_label, type="primary" if draft_count > 0 else "secondary", use_container_width=True, key="btn_apply_single_draft"):
                if draft_ab:
                    for kw, status in draft_ab.items():
                        if status == "NG":
                            current_ng.add(kw)
                            current_ok.discard(kw)
                        elif status == "OK":
                            current_ok.add(kw)
                            current_ng.discard(kw)
                        elif status == "RESET":
                            current_ng.discard(kw)
                            current_ok.discard(kw)
                    draft_ab.clear()
                    
                    save_dict = {}
                    for k in current_ng: save_dict[k] = "NG"
                    for k in current_ok: save_dict[k] = "OK"
                    safe_save_json(save_dict, about_rules_path)

                    st.session_state["chk_view_ver"] += 1
                    st.success("🎉 仮判定をルールへ一括適用し、件数計算を更新しました！")
                    st.rerun()
                else:
                    st.info("現在仮選択中のキーワードはありません。")

    with tab_llm:
        st.markdown("🎯 **【全体ノイズ検知】**: 残したい目的キーワードを指定してデータセット全体から無関係な単語を自動検出します。")
        default_targets = list(current_ok) if current_ok else st.session_state.get("expansion_res", {}).get("keywords", ["楽譜", "音楽", "音譜", "能楽", "三味線"])
        target_input = st.text_input("残したい目的(ターゲット)キーワード (カンマ区切り):", value=", ".join(default_targets), key="txt_target_kws_tab")

        c_top1, c_top2 = st.columns([3, 1])
        with c_top1:
            st.caption("AI提案結果からノイズ候補を一括選択してNG登録できます。")
        with c_top2:
            if st.button("🤖 全体から無関係単語をNG提案", type="primary", use_container_width=True, key="btn_suggest_llm_ng"):
                sample_kws = [k for k, c in about_ranking[:60]]
                domain_def = st.session_state.get("expansion_res", {}).get("domain_definition", "日本の文化資源・資料")
                target_kws_list = [t.strip() for t in target_input.split(",") if t.strip()]

                with st.spinner("LLMがデータセット全体からノイズ単語を分析中..."):
                    cfg = st.session_state.get("llm_config", {})
                    suggs = suggest_ng_keywords_with_llm(
                        current_ng_list=list(current_ng), 
                        sample_keywords=sample_kws, 
                        target_keywords=target_kws_list,
                        domain_definition=domain_def,
                        provider=cfg.get("provider", "local"),
                        api_base=cfg.get("api_base", "http://localhost:1234/v1"),
                        api_key=cfg.get("api_key", ""),
                        model=cfg.get("model", "local-model")
                    )
                    st.session_state["llm_about_suggs"] = suggs

        if "llm_about_suggs" in st.session_state:
            suggs = st.session_state["llm_about_suggs"]
            st.warning(f"💡 **LLMが全体検知したノイズ候補 (全 {len(suggs)} 個)**")
            selected_suggs = st.multiselect("一括登録するキーワードを選択:", options=suggs, default=suggs, key="ms_llm_suggs")
            if st.button("✨ 選択したノイズ候補をNGリストに追加", type="primary", key="btn_add_llm_suggs_ng"):
                if selected_suggs:
                    current_ng.update(selected_suggs)
                    st.success(f"{len(selected_suggs)} 件をNGリストに追加しました！")
                    st.session_state.pop("llm_about_suggs", None)
                    st.rerun()

    col_act1, col_act2, col_act3 = st.columns([3, 3, 2])
    with col_act1:
        if st.button("🚫 チェック選択中のキーワードを NG リストに追加", type="primary", use_container_width=True):
            if checked_words:
                to_add = list(checked_words)
                current_ng.update(to_add)
                for k in to_add: current_ok.discard(k)
                checked_words.clear()
                st.session_state["chk_view_ver"] += 1
                st.success(f"{len(to_add)} 件のキーワードを NG リストに追加しました。")
                st.rerun()
            else:
                st.warning("チェックされているキーワードがありません。")

    with col_act2:
        if st.button("✅ チェック選択中のキーワードを OK リストに追加", use_container_width=True):
            if checked_words:
                to_add = list(checked_words)
                current_ok.update(to_add)
                for k in to_add: current_ng.discard(k)
                checked_words.clear()
                st.session_state["chk_view_ver"] += 1
                st.success(f"{len(to_add)} 件のキーワードを OK リストに追加しました。")
                st.rerun()

    st.write("---")
    c_save1, c_save2, c_reset = st.columns([2, 1, 1])
    with c_save1:
        st.caption("仕分け結果は『rules.json に保存する』ボタンを押すと次回以降も永続保持されます。")
    with c_save2:
        if st.button("💾 About rules.json に保存する", type="primary", use_container_width=True):
            save_dict = {}
            for k in current_ng: save_dict[k] = "NG"
            for k in current_ok: save_dict[k] = "OK"
            safe_save_json(save_dict, about_rules_path)
            st.success("🎉 rules.json に保存しました！")

    with c_reset:
        with st.popover("🗑️ ルール全リセット", help="Aboutルールを初期化クリア"):
            st.warning("⚠️ 本当に About ルール (`about_rules.json`) を全リセットしますか？")
            st.caption("登録済みの全 NG / OK パターンおよび仮判定データが完全に消去されます。")
            if st.button("💥 確定して全リセットする", type="primary", use_container_width=True, key="btn_confirm_reset_about"):
                st.session_state["edited_noise"] = set()
                st.session_state["edited_strong"] = set()
                st.session_state["draft_about_changes"] = {}
                safe_save_json({}, about_rules_path)
                
                data_dir = os.path.dirname(about_filtered_path)
                for p_rm in [about_filtered_path, f"{data_dir}/discarded_about.csv"]:
                    if os.path.exists(p_rm):
                        try:
                            os.remove(p_rm)
                        except Exception:
                            pass
                st.cache_data.clear()
                st.session_state["chk_view_ver"] += 1
                st.success("🎉 About ルール (about_rules.json) およびフィルタ結果を完全にリセットしました！")
                st.rerun()

    st.write("---")
    st.subheader("▶️ About フィルタの適用実行")
    if st.button("About フィルタを実行してノイズデータを除外する", type="primary", use_container_width=True):
        save_dict = {}
        for k in current_ng: save_dict[k] = "NG"
        for k in current_ok: save_dict[k] = "OK"
        safe_save_json(save_dict, about_rules_path)

        data_dir = os.path.dirname(about_filtered_path)
        passed, disc = run_about_filter(raw_metadata_path, about_rules_path, about_filtered_path, f"{data_dir}/discarded_about.csv")
        st.cache_data.clear()
        st.success(f"🎉 About フィルタ適用完了: 通過 {passed} 件 / 除外 {disc} 件 (除外ログ: {data_dir}/discarded_about.csv)")
