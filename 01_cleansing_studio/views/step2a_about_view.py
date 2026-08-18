# -*- coding: utf-8 -*-
"""
MetaClean Studio - Step 2-A: 主題 (schema:about) キーワード分析・判別ビュー
"""
import json
import math
import os
import re
from collections import defaultdict
import streamlit as st

from components.file_utils import safe_save_json, make_rich_search_links_md, make_rich_search_links
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
    st.title("Step 2-A: 主題 (schema:about) キーワード分析・判別")
    st.markdown("取得データに含まれる `schema:about` キーワード一覧を解析し、対象ドメイン外の除外対象（NG）および保持対象（OK）のカテゴリ判別を行います。")

    raw_metadata_path = paths['PATH_RAW_METADATA']
    about_rules_path = paths['PATH_ABOUT_RULES']
    about_filtered_path = paths['PATH_ABOUT_FILTERED']

    if not os.path.exists(raw_metadata_path):
        st.warning("先に Step 1 で生メタデータ (raw_metadata.jsonl) を取得してください。")
        st.stop()

    os.makedirs(os.path.dirname(about_rules_path), exist_ok=True)
    
    raw_mtime = os.path.getmtime(raw_metadata_path) if os.path.exists(raw_metadata_path) else 0

    @st.cache_resource(show_spinner=False)
    def load_raw_item_features(path, mtime):
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

                        desc_val = item.get("schema:description", "")
                        desc_str = str(desc_val[0]) if isinstance(desc_val, list) and desc_val else str(desc_val)

                        creator_val = item.get("schema:creator", "")
                        creator_str = str(creator_val[0]) if isinstance(creator_val, list) and creator_val else str(creator_val)

                        records_data.append({
                            "id": item.get("@id", item.get("id", "")),
                            "title": title_str,
                            "desc": desc_str,
                            "creator": creator_str,
                            "about_set": kw_set
                        })
                        for kw in kw_set:
                            kw_to_doc_indices[kw].append(idx)
                        idx += 1
                    except Exception:
                        continue
        return about_ranking, records_data, kw_to_doc_indices

    about_ranking, raw_records, kw_to_doc_indices = load_raw_item_features(raw_metadata_path, raw_mtime)

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

    # レコード（メタデータ件数）ベースの高速シミュレーション
    total_records_cnt = len(raw_records)
    
    ng_doc_indices = set()
    for ng_kw in current_ng:
        # 完全一致をまず高速取得
        if ng_kw in kw_to_doc_indices:
            ng_doc_indices.update(kw_to_doc_indices[ng_kw])
        # 部分一致の補完
        for kw, doc_indices in kw_to_doc_indices.items():
            if kw != ng_kw and ng_kw in kw:
                ng_doc_indices.update(doc_indices)

    ok_doc_indices = set()
    for ok_kw in current_ok:
        if ok_kw in kw_to_doc_indices:
            ok_doc_indices.update([i for i in kw_to_doc_indices[ok_kw] if i not in ng_doc_indices])
        for kw, doc_indices in kw_to_doc_indices.items():
            if kw != ok_kw and ok_kw in kw:
                ok_doc_indices.update([i for i in doc_indices if i not in ng_doc_indices])

    active_doc_indices = set(range(total_records_cnt)) - ng_doc_indices
    discarded_records_cnt = len(ng_doc_indices)
    ok_records_cnt = len(ok_doc_indices)
    remaining_records_cnt = len(active_doc_indices)
    reduction_rate = discarded_records_cnt / max(1, total_records_cnt)

    total_about_types = len(about_ranking)
    all_kw_set = set([k for k, c in about_ranking])
    ng_classified_count = len(all_kw_set & current_ng)
    ok_classified_count = len(all_kw_set & current_ok)
    unclassified_count = total_about_types - ng_classified_count - ok_classified_count

    st.subheader("Aboutルール適用によるメタデータ絞り込み進捗（レコード件数ベース）")
    m_col1, m_col2, m_col3, m_col4 = st.columns(4)
    with m_col1:
        st.metric("母集団 Raw レコード", f"{total_records_cnt:,} 件")
    with m_col2:
        st.metric(
            "About除外対象 (削ぎ落とし)", 
            f"{discarded_records_cnt:,} 件", 
            delta=f"-{reduction_rate:.1%}", 
            delta_color="inverse",
            help="schema:aboutにNGキーワードが含まれるため本工程で除外されるメタデータ件数"
        )
    with m_col3:
        st.metric(
            "本工程通過残存レコード", 
            f"{remaining_records_cnt:,} 件", 
            delta=f"{remaining_records_cnt/max(1, total_records_cnt):.1%}",
            help="NGルールを除外し、次の工程へ引き継がれるメタデータ件数"
        )
    with m_col4:
        st.metric(
            "キーワード判別進捗", 
            f"全 {total_about_types:,} 語",
            delta=f"NG: {ng_classified_count} / OK: {ok_classified_count} / 未: {unclassified_count}",
            help="登録されたNG/OKキーワードの総種類数"
        )

    with st.expander(f"現在の About NG / OK 登録リスト (NG: {len(current_ng)} 語 / OK: {len(current_ok)} 語)", expanded=False):
        c_manage_ng, c_manage_ok = st.columns(2)
        with c_manage_ng:
            st.markdown(f"### 除外(NG) リスト ({len(current_ng)} 語)")
            if current_ng:
                ng_list_sorted = sorted(list(current_ng))
                try:
                    selected_ab_ng_pills = st.pills("選択して削除する項目をクリック:", options=ng_list_sorted, selection_mode="multi", key="pills_about_ng")
                except AttributeError:
                    selected_ab_ng_pills = st.multiselect("削除する項目を選択:", options=ng_list_sorted, key="ms_about_ng_fallback")

                if st.button("選択項目の NG リストからの解除", key="btn_del_ab_ng_pills", type="primary", use_container_width=True):
                    if selected_ab_ng_pills:
                        current_ng.difference_update(selected_ab_ng_pills)
                        st.session_state["chk_view_ver"] += 1
                        st.success(f"{len(selected_ab_ng_pills)} 件の項目を NG リストから削除しました。")
                        st.rerun()
                    else:
                        st.warning("解除する項目が選択されていません。")
            else:
                st.info("NG リストは現在空です。")

        with c_manage_ok:
            st.markdown(f"### 保持(OK) リスト ({len(current_ok)} 語)")
            if current_ok:
                ok_list_sorted = sorted(list(current_ok))
                try:
                    selected_ab_ok_pills = st.pills("選択して削除する項目をクリック:", options=ok_list_sorted, selection_mode="multi", key="pills_about_ok")
                except AttributeError:
                    selected_ab_ok_pills = st.multiselect("削除する項目を選択:", options=ok_list_sorted, key="ms_about_ok_fallback")

                if st.button("選択項目の OK リストからの解除", key="btn_del_ab_ok_pills", type="primary", use_container_width=True):
                    if selected_ab_ok_pills:
                        current_ok.difference_update(selected_ab_ok_pills)
                        st.session_state["chk_view_ver"] += 1
                        st.success(f"{len(selected_ab_ok_pills)} 件の項目を OK リストから削除しました。")
                        st.rerun()
                    else:
                        st.warning("解除する項目が選択されていません。")
            else:
                st.info("OK リストは現在空です。")

    st.write("---")

    @st.cache_resource(show_spinner=False)
    def get_cached_about_clusters(about_ranking_list):
        return cluster_about_keywords(about_ranking_list)

    about_clusters = get_cached_about_clusters(about_ranking)

    tab_custom, tab_cluster, tab_single, tab_llm = st.tabs([
        "🎯 自由入力キーワード一括指定 (カスタム指定)",
        "クラスタ一括判別 (推奨)",
        "単体キーワード判別ボード",
        "LLMによるノイズ候補提案"
    ])

    # =========================================================================
    # TAB 1: 自由入力キーワード一括指定 (カスタム指定)
    # =========================================================================
    with tab_custom:
        st.markdown("### 自由入力による About キーワード除外・保持指定")
        st.caption("主題 (schema:about) に含まれる特定の単語やジャンル（例: 政治, 法律, 経済, 医学, 地理 など）を入力し、ヒットする資料を確認しながら一括除外・保持指定できます。")

        custom_about_input = st.text_area(
            "除外・保持したい About キーワード (カンマ、読点、または改行区切りで複数入力可能):",
            placeholder="例: 政治, 法律, 経済, 医学, 理学, 仏教, 哲学",
            height=80,
            key="txt_custom_about_kws"
        )

        parsed_custom_about = [
            w.strip() for w in re.split(r"[\n,、・/／\s]+", custom_about_input) if len(w.strip()) >= 1
        ]
        parsed_custom_about = list(dict.fromkeys(parsed_custom_about))

        if parsed_custom_about:
            st.markdown(f"#### 🔍 入力された {len(parsed_custom_about)} 件のキーワードのヒット検証")
            
            kw_hit_stats = []
            total_impact_docs = set()
            active_impact_docs = set()

            for kw in parsed_custom_about:
                matched_about_kws = [k for k, c in about_ranking if kw in k]
                
                doc_indices_for_kw = set()
                for mk in matched_about_kws:
                    doc_indices_for_kw.update(kw_to_doc_indices.get(mk, []))
                
                total_impact_docs.update(doc_indices_for_kw)
                act_docs = [i for i in doc_indices_for_kw if i in active_doc_indices]
                active_impact_docs.update(act_docs)
                
                is_currently_ng = kw in current_ng
                is_currently_ok = kw in current_ok
                
                samples_list = []
                for i in list(doc_indices_for_kw)[:15]:
                    rec = raw_records[i]
                    samples_list.append({
                        "id": rec.get("id", ""),
                        "title": rec.get("title", ""),
                        "desc": rec.get("desc", ""),
                        "creator": rec.get("creator", "")
                    })

                kw_hit_stats.append({
                    "keyword": kw,
                    "matched_about": matched_about_kws,
                    "total_hits": len(doc_indices_for_kw),
                    "active_hits": len(act_docs),
                    "samples": samples_list,
                    "status": "NG" if is_currently_ng else ("OK" if is_currently_ok else "未登録")
                })

            c_s1, c_s2, c_s3 = st.columns(3)
            with c_s1:
                st.metric("指定キーワード総数", f"{len(parsed_custom_about)} 語")
            with c_s2:
                st.metric("ヒットする母集団レコード", f"{len(total_impact_docs):,} 件", help="全母データ中でいずれかのキーワードを含む資料数")
            with c_s3:
                st.metric("本工程での新規除外インパクト", f"{len(active_impact_docs):,} 件", delta=f"-{len(active_impact_docs):,} 件", delta_color="inverse", help="現在まだ除外されていないデータから新たに削ぎ落とされる件数")

            c_a1, c_a2, c_a3 = st.columns([2, 2, 1])
            with c_a1:
                if st.button(f"🚫 指定した {len(parsed_custom_about)} 語を一括で NG (除外) ルールへ追加", type="primary", use_container_width=True, key="btn_apply_about_custom_ng"):
                    for kw in parsed_custom_about:
                        current_ng.add(kw)
                        current_ok.discard(kw)
                    save_dict = {k: "NG" for k in current_ng}
                    save_dict.update({k: "OK" for k in current_ok})
                    safe_save_json(save_dict, about_rules_path)
                    st.session_state["chk_view_ver"] += 1
                    st.cache_data.clear()
                    st.success(f"{len(parsed_custom_about)} 件のキーワードを NG ルールへ登録しました。")
                    st.rerun()

            with c_a2:
                if st.button(f"✅ 指定した {len(parsed_custom_about)} 語を一括で OK (保持) ルールへ追加", type="secondary", use_container_width=True, key="btn_apply_about_custom_ok"):
                    for kw in parsed_custom_about:
                        current_ok.add(kw)
                        current_ng.discard(kw)
                    save_dict = {k: "NG" for k in current_ng}
                    save_dict.update({k: "OK" for k in current_ok})
                    safe_save_json(save_dict, about_rules_path)
                    st.session_state["chk_view_ver"] += 1
                    st.cache_data.clear()
                    st.success(f"{len(parsed_custom_about)} 件のキーワードを OK ルールへ登録しました。")
                    st.rerun()

            with c_a3:
                if st.button("🔄 入力クリア", use_container_width=True, key="btn_clear_about_custom_input"):
                    st.session_state["txt_custom_about_kws"] = ""
                    st.rerun()

            st.write("---")
            st.markdown("##### 📋 キーワード別ヒット詳細 ＆ 該当資料プレビュー")
            for stat in kw_hit_stats:
                kw = stat["keyword"]
                tot_h = stat["total_hits"]
                act_h = stat["active_hits"]
                cur_st = stat["status"]
                m_abouts = stat["matched_about"]

                if cur_st == "NG":
                    st_badge = "🚫 [NG登録済]"
                elif cur_st == "OK":
                    st_badge = "✅ [OK登録済]"
                else:
                    st_badge = "❓ [未登録]"

                exp_header = f"『{kw}』 ➔ 全 {tot_h:,} 件ヒット (未判定: {act_h:,} 件 / 一致About: {len(m_abouts)}種類) ｜ {st_badge}"
                with st.expander(exp_header, expanded=(tot_h > 0 and cur_st == "未登録")):
                    c_ak1, c_ak2 = st.columns([3, 1])
                    with c_ak1:
                        st.markdown(make_rich_search_links_md(kw))
                        if m_abouts:
                            st.caption(f"一致したAboutキーワード: {', '.join(m_abouts[:10])}{'...' if len(m_abouts)>10 else ''}")
                    with c_ak2:
                        if cur_st != "NG":
                            if st.button(f"🚫 『{kw}』をNGに登録", key=f"btn_cust_ab_ng_{kw}", use_container_width=True):
                                current_ng.add(kw)
                                current_ok.discard(kw)
                                save_dict = {k: "NG" for k in current_ng}
                                save_dict.update({k: "OK" for k in current_ok})
                                safe_save_json(save_dict, about_rules_path)
                                st.session_state["chk_view_ver"] += 1
                                st.cache_data.clear()
                                st.rerun()
                        else:
                            if st.button(f"↩️ 『{kw}』をNG解除", key=f"btn_cust_ab_del_{kw}", use_container_width=True):
                                current_ng.discard(kw)
                                save_dict = {k: "NG" for k in current_ng}
                                save_dict.update({k: "OK" for k in current_ok})
                                safe_save_json(save_dict, about_rules_path)
                                st.session_state["chk_view_ver"] += 1
                                st.cache_data.clear()
                                st.rerun()

                    st.caption(f"該当資料の具体例 (先頭 {len(stat['samples'])} 件):")
                    with st.container(height=200):
                        for s in stat["samples"]:
                            st.markdown(f"**📖 {s['title']}**")
                            meta_p = []
                            if s.get('creator'): meta_p.append(f"著者: `{s['creator']}`")
                            if s.get('id'): meta_p.append(f"[🔗 Japan Search]({s['id']})")
                            if meta_p: st.caption(" ｜ ".join(meta_p))
                            if s.get('desc'):
                                st.markdown(f"<div style='font-size:0.8rem; color:#bbb;'>{s['desc'][:120]}...</div>", unsafe_allow_html=True)
                            st.markdown("<hr style='margin:4px 0; border:0; border-top:1px solid rgba(255,255,255,0.08);'/>", unsafe_allow_html=True)
        else:
            st.info("上記テキストエリアに除外したい単語（例: `政治, 法律, 経済, 医学`）を入力すると、一致するAboutキーワードの検出と一括除外が行えます。")

    with tab_cluster:
        st.markdown("類似性に基づいて抽出されたキーワード群に対し仮選択（OK/NG/未判定）を行い、一括確定を適用します。")

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
                    st.warning(f"現在 {draft_count} 件のキーワードが仮選択中です（未適用）。")
                else:
                    st.caption("各クラスタで OK / NG を仮選択し、「一括確定して適用」ボタンで更新してください。")
            with c_cl_hdr2:
                btn_apply_label = f"仮設定 ({draft_count} 件) の一括適用" if draft_count > 0 else "判定の一括適用"
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
                        st.success("クラスタ判別結果を about_rules.json へ保存・適用しました。")
                        st.rerun()
                    else:
                        st.info("現在仮選択中のキーワードはありません。")

            st.write("---")

            ctrl_col1, ctrl_col2, ctrl_col3 = st.columns([3, 2, 2])
            with ctrl_col1:
                hide_fully_classified = st.checkbox("判定済みのクラスタを非表示にする", value=False, key="chk_hide_classified_clusters")
            with ctrl_col2:
                sort_cluster_by = st.selectbox("ソート順:", ["合計データ件数順", "所属キーワード数順"], key="sb_cluster_sort")
            with ctrl_col3:
                clusters_per_page = st.number_input("1ページ表示数", min_value=5, max_value=100, value=10, step=5, key="num_clusters_per_page")

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
                st.success("表示条件に一致する未判定のクラスタはありません。")
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
                    st.rerun()
            with p_col2:
                st.markdown(f"<div style='text-align: center; padding-top: 6px;'><b>全 {total_display_clusters} クラスタ中 {current_page} / {total_pages} ページを表示</b></div>", unsafe_allow_html=True)
            with p_col3:
                if st.button("次のページ ▶", disabled=(current_page >= total_pages), key="btn_next_cluster_page", use_container_width=True):
                    st.session_state["cluster_page_idx"] = min(total_pages, current_page + 1)
                    st.rerun()

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
                    status_badge = "全除外 (NG)"
                elif ok_c > 0 and ng_c == 0 and un_c == 0:
                    status_badge = "全保持 (OK)"
                elif ok_c > 0 or ng_c > 0:
                    status_badge = f"混合 (OK:{ok_c} / NG:{ng_c} / 未:{un_c})"
                else:
                    status_badge = f"未判定 (全{un_c}件)"

                kw_preview = ", ".join(kws[:5]) + ("..." if len(kws) > 5 else "")
                expander_title = f"{c['name']} ➔ [{status_badge}] （対象語句: {kw_preview} [{len(kws)}種類] / 件数: {c['total_count']:,} 件）"

                with st.expander(expander_title, expanded=(un_c > 0)):
                    b_col1, b_col2, b_col3 = st.columns(3)
                    with b_col1:
                        if st.button(f"一括 OK 仮設定 [{len(kws)}件]", key=f"btn_cl_ok_{cid}", type="secondary", use_container_width=True):
                            for k in kws:
                                draft_ab[k] = "OK"
                            st.rerun()
                    with b_col2:
                        if st.button(f"一括 NG 仮設定 [{len(kws)}件]", key=f"btn_cl_ng_{cid}", type="primary", use_container_width=True):
                            for k in kws:
                                draft_ab[k] = "NG"
                            st.rerun()
                    with b_col3:
                        if st.button(f"一括 未判定リセット", key=f"btn_cl_reset_{cid}", use_container_width=True):
                            for k in kws:
                                draft_ab[k] = "RESET"
                            st.rerun()

                    st.caption("個別切替 (クリックで OK / NG / 未判定 がトグル切替、🔍 で検索・資料詳細):")
                    cl_cols = st.columns(3)
                    for idx_k, kw in enumerate(kws):
                        col_k = cl_cols[idx_k % 3]
                        st_val = get_eff_status(kw)
                        
                        if st_val == "OK":
                            lbl = f"✅ {kw}"
                        elif st_val == "NG":
                            lbl = f"🚫 {kw}"
                        else:
                            lbl = f"❓ {kw}"

                        kw_indices = kw_to_doc_indices.get(kw, [])

                        c_btn_k, c_pop_k = col_k.columns([5, 1])
                        with c_btn_k:
                            if st.button(lbl, key=f"tgl_kw_{cid}_{kw}", use_container_width=True):
                                if st_val == "OK":
                                    draft_ab[kw] = "NG"
                                elif st_val == "NG":
                                    draft_ab[kw] = "RESET"
                                else:
                                    draft_ab[kw] = "OK"
                                st.rerun()
                        with c_pop_k:
                            with st.popover("🔍", help=f"『{kw}』の外部検索・該当資料詳細"):
                                st.markdown(f"### 🔍 『{kw}』")
                                st.markdown(make_rich_search_links_md(kw))
                                st.markdown(f"- 出現資料件数: **{len(kw_indices):,} 件**")
                                st.write("---")
                                st.caption(f"📄 出現資料サンプル (先頭 {min(15, len(kw_indices))} 件):")
                                with st.container(height=260):
                                    for idx_doc in kw_indices[:15]:
                                        rec = raw_records[idx_doc]
                                        st.markdown(f"**📖 {rec['title']}**")
                                        meta_items = []
                                        if rec.get('creator'): meta_items.append(f"著者: `{rec['creator']}`")
                                        if rec.get('id'): meta_items.append(f"[🔗 Japan Search]({rec['id']})")
                                        if meta_items: st.caption(" ｜ ".join(meta_items))
                                        if rec.get('desc'):
                                            st.markdown(f"<div style='font-size:0.8rem; color:#bbb; background:rgba(255,255,255,0.04); padding:3px 6px; border-radius:3px;'>{rec['desc'][:120]}...</div>", unsafe_allow_html=True)
                                        st.markdown("<hr style='margin:4px 0; border:0; border-top:1px solid rgba(255,255,255,0.08);'/>", unsafe_allow_html=True)

        render_cluster_board()

    with tab_single:
        col_opt1, col_opt2 = st.columns([3, 2])
        with col_opt1:
            view_filter_mode = st.radio(
                "表示オプション:", 
                options=["すべて表示", "未判定のみ", "NGのみ", "OKのみ"], 
                horizontal=True,
                key="view_filter_about_mode"
            )
            is_unclassified_mode = (view_filter_mode == "未判定のみ")
            hide_zero_about = st.checkbox(
                "残存未判定件数が 0 件のキーワードを非表示にする", 
                value=True, 
                disabled=not is_unclassified_mode,
                key="chk_hide_zero_about"
            )
        with col_opt2:
            search_query = st.text_input("キーワード検索:", placeholder="例: 演劇 -能", key="q_about_pills")

        if "click_action_about_mode" not in st.session_state:
            st.session_state["click_action_about_mode"] = "NGに設定"

        st.caption("判定モード切替 (ショートカット: Q / W / E キー):")
        c_m1, c_m2, c_m3 = st.columns(3)
        
        btn1_type = "primary" if st.session_state["click_action_about_mode"] == "NGに設定" else "secondary"
        btn2_type = "primary" if st.session_state["click_action_about_mode"] == "OKに設定" else "secondary"
        btn3_type = "primary" if st.session_state["click_action_about_mode"] == "未判定に戻す" else "secondary"

        b1 = c_m1.button("【 Q 】 NG設定モード", key="btn_shortcut_ab_q", type=btn1_type, use_container_width=True)
        b2 = c_m2.button("【 W 】 OK設定モード", key="btn_shortcut_ab_w", type=btn2_type, use_container_width=True)
        b3 = c_m3.button("【 E 】 未判定リセット", key="btn_shortcut_ab_e", type=btn3_type, use_container_width=True)

        if hotkeys:
            if hotkeys.pressed("mode_ng"):
                st.session_state["click_action_about_mode"] = "NGに設定"
                st.rerun()
            elif hotkeys.pressed("mode_ok"):
                st.session_state["click_action_about_mode"] = "OKに設定"
                st.rerun()
            elif hotkeys.pressed("mode_reset"):
                st.session_state["click_action_about_mode"] = "未判定に戻す"
                st.rerun()

        if b1:
            st.session_state["click_action_about_mode"] = "NGに設定"
            st.rerun()
        if b2:
            st.session_state["click_action_about_mode"] = "OKに設定"
            st.rerun()
        if b3:
            st.session_state["click_action_about_mode"] = "未判定に戻す"
            st.rerun()

        click_action_mode = st.session_state["click_action_about_mode"]

        if click_action_mode == "NGに設定":
            st.error("【現在の設定モード: NG (除外)】 (ショートカット: Q)")
        elif click_action_mode == "OKに設定":
            st.success("【現在の設定モード: OK (保持)】 (ショートカット: W)")
        elif click_action_mode == "未判定に戻す":
            st.info("【現在の設定モード: 未判定リセット】 (ショートカット: E)")

        filtered_ranking = about_ranking
        if view_filter_mode == "未判定のみ":
            filtered_ranking = [(k, c) for k, c in filtered_ranking if k not in current_ng and k not in current_ok]
        elif view_filter_mode == "NGのみ":
            filtered_ranking = [(k, c) for k, c in filtered_ranking if k in current_ng]
        elif view_filter_mode == "OKのみ":
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
            samples_list = []
            for i in act_indices[:30]:
                rec = raw_records[i]
                samples_list.append({
                    "id": rec.get("id", ""),
                    "title": rec.get("title", ""),
                    "desc": rec.get("desc", ""),
                    "creator": rec.get("creator", "")
                })
            active_samples_info[kw] = {
                "eff_cnt": len(act_indices),
                "samples": samples_list
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
            st.markdown(f"判定対象キーワード (該当: **{len(filtered_ranking)}** 件)")
        with c_hdr2:
            draft_count = len(draft_ab)
            btn_apply_label = f"仮設定 ({draft_count} 件) の一括適用" if draft_count > 0 else "判定の一括適用"
            if st.button(btn_apply_label, type="primary" if draft_count > 0 else "secondary", use_container_width=True, key="btn_single_draft_apply"):
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
                    st.success("仮判定をルールへ一括適用しました。")
                    st.rerun()
                else:
                    st.info("現在仮選択中のキーワードはありません。")

    with tab_llm:
        st.markdown("【全域ノイズ判定アシスト】: 保持したいドメイン中心語を指定し、データセット全体から対象外キーワードの候補をLLMで自動抽出します。")
        default_targets = list(current_ok) if current_ok else st.session_state.get("expansion_res", {}).get("keywords", ["楽譜", "音楽", "音譜", "能楽", "三味線"])
        target_input = st.text_input("保持対象 (ターゲット) キーワード (カンマ区切り):", value=", ".join(default_targets), key="txt_target_kws_tab")

        c_top1, c_top2 = st.columns([3, 1])
        with c_top1:
            st.caption("抽出されたノイズ候補を選択し、一括で NG リストへ登録できます。")
        with c_top2:
            if st.button("LLMによるノイズ候補の提案", type="primary", use_container_width=True, key="btn_suggest_llm_ng"):
                sample_kws = [k for k, c in about_ranking[:60]]
                domain_def = st.session_state.get("expansion_res", {}).get("domain_definition", "日本の文化資源・資料")
                target_kws_list = [t.strip() for t in target_input.split(",") if t.strip()]

                with st.spinner("LLMがデータセット全体から対象外キーワードを抽出中..."):
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
            st.warning(f"LLMが抽出したノイズ候補 (全 {len(suggs)} 件)")
            selected_suggs = st.multiselect("一括登録するキーワードの選択:", options=suggs, default=suggs, key="ms_llm_suggs")
            if st.button("選択したノイズ候補を NG リストに追加", type="primary", key="btn_add_llm_suggs_ng"):
                if selected_suggs:
                    current_ng.update(selected_suggs)
                    st.success(f"{len(selected_suggs)} 件を NG リストに追加しました。")
                    st.session_state.pop("llm_about_suggs", None)
                    st.rerun()

    col_act1, col_act2, col_act3 = st.columns([3, 3, 2])
    with col_act1:
        if st.button("選択中のキーワードを NG リストに追加", type="primary", use_container_width=True):
            if checked_words:
                to_add = list(checked_words)
                current_ng.update(to_add)
                for k in to_add: current_ok.discard(k)
                checked_words.clear()
                st.session_state["chk_view_ver"] += 1
                st.success(f"{len(to_add)} 件のキーワードを NG リストに追加しました。")
                st.rerun()
            else:
                st.warning("選択されているキーワードがありません。")

    with col_act2:
        if st.button("選択中のキーワードを OK リストに追加", use_container_width=True):
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
        st.caption("設定は「about_rules.json に保存する」ボタンを押すとファイルへ永続保存されます。")
    with c_save2:
        if st.button("about_rules.json に保存する", type="primary", use_container_width=True):
            save_dict = {}
            for k in current_ng: save_dict[k] = "NG"
            for k in current_ok: save_dict[k] = "OK"
            safe_save_json(save_dict, about_rules_path)
            st.success("about_rules.json に設定を保存しました。")

    with c_reset:
        with st.popover("ルール全初期化", help="Aboutルールを初期化"):
            st.warning("About ルール設定 (about_rules.json) を全初期化しますか？")
            st.caption("登録済みの NG / OK パターンがすべて初期化されます。")
            if st.button("確定して初期化を実行", type="primary", use_container_width=True, key="btn_confirm_reset_about"):
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
                st.success("About ルールおよびフィルタ適用結果を初期化しました。")
                st.rerun()

    st.write("---")
    st.subheader("About ルールフィルタの適用実行")
    if st.button("About ルールフィルタリングを実行してノイズを除外する", type="primary", use_container_width=True):
        save_dict = {}
        for k in current_ng: save_dict[k] = "NG"
        for k in current_ok: save_dict[k] = "OK"
        safe_save_json(save_dict, about_rules_path)

        data_dir = os.path.dirname(about_filtered_path)
        passed, disc = run_about_filter(raw_metadata_path, about_rules_path, about_filtered_path, f"{data_dir}/discarded_about.csv")
        st.cache_data.clear()
        st.success(f"About ルールフィルタリング完了: 通過 {passed:,} 件 / 除外 {disc:,} 件 (除外ログ: {data_dir}/discarded_about.csv)")
