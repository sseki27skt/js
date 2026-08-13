# -*- coding: utf-8 -*-
"""
MetaClean Studio - Step 2-B: タイトル N-Gram (N=2〜9) パターン分析・除外ビュー
"""
import json
import math
import os
import re
from collections import Counter, defaultdict
import streamlit as st

from components.file_utils import safe_save_json
from components.pill_board import render_pill_board
from modules.ngram_filter import extract_ngrams_from_jsonl, run_ngram_filter, clean_title_text

try:
    import streamlit_hotkeys as hotkeys
except Exception:
    hotkeys = None


def render_step2b_view(paths: dict):
    """Step 2-B 画面の描画"""
    st.title("Step 2-B: タイトル N-Gram (N=2〜9) パターン分析・除外")
    st.markdown("資料タイトルに含まれる N=2 〜 9 文字の頻出部分文字列（例: 〜日記, 〜家譜, 〜楽譜, 〜演劇 など）を集計・抽出し、除外パターンの選定を行います。")

    about_filtered_path = paths['PATH_ABOUT_FILTERED']
    raw_metadata_path = paths['PATH_RAW_METADATA']
    ngram_rules_path = paths['PATH_NGRAM_RULES']
    ngram_filtered_path = paths['PATH_NGRAM_FILTERED']
    data_dir = os.path.dirname(ngram_filtered_path)

    input_path = about_filtered_path if os.path.exists(about_filtered_path) else raw_metadata_path
    if not os.path.exists(input_path):
        st.warning("対象データが存在しません。Step 1 を実行してください。")
        st.stop()

    os.makedirs(os.path.dirname(ngram_rules_path), exist_ok=True)
    if "edited_ngram_ng" not in st.session_state:
        ngram_rules = {}
        if os.path.exists(ngram_rules_path):
            with open(ngram_rules_path, 'r', encoding='utf-8') as f:
                ngram_rules = json.load(f)
        st.session_state["edited_ngram_ng"] = set([k for k, v in ngram_rules.items() if v == "NG"])
        st.session_state["edited_ngram_ok"] = set([k for k, v in ngram_rules.items() if v == "OK"])

    if "ngram_view_ver" not in st.session_state:
        st.session_state["ngram_view_ver"] = 0

    ngram_ng = st.session_state["edited_ngram_ng"]
    ngram_ok = st.session_state["edited_ngram_ok"]

    @st.cache_data(show_spinner=False)
    def load_filtered_titles(file_path, file_mtime):
        titles_data = []
        if os.path.exists(file_path):
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                for line in f:
                    if not line.strip(): continue
                    try:
                        item = json.loads(line)
                        label_val = item.get("rdfs:label", item.get("schema:name", ""))
                        title_str = str(label_val[0]) if isinstance(label_val, list) and label_val else str(label_val)
                        titles_data.append(title_str)
                    except Exception:
                        continue
        return titles_data

    input_mtime = os.path.getmtime(input_path) if os.path.exists(input_path) else 0
    input_titles = load_filtered_titles(input_path, input_mtime)

    @st.cache_data(show_spinner=False)
    def get_cached_ngrams_from_titles_fast(file_path, file_mtime, min_n=2, max_n=9):
        titles = load_filtered_titles(file_path, file_mtime)
        counts = {n: Counter() for n in range(min_n, max_n + 1)}
        samples = {n: defaultdict(list) for n in range(min_n, max_n + 1)}

        for title in titles:
            clean_title = clean_title_text(title)
            for n in range(min_n, max_n + 1):
                if len(clean_title) >= n:
                    ngrams = [clean_title[i:i+n] for i in range(len(clean_title) - n + 1)]
                    for word in set(ngrams):
                        counts[n][word] += 1
                        if len(samples[n][word]) < 30 and title not in samples[n][word]:
                            samples[n][word].append(title)

        result_dict = {}
        for n in range(min_n, max_n + 1):
            ranking = []
            for word, count in counts[n].most_common(500):
                if count >= 2:
                    ranking.append((word, count, samples[n][word]))
            result_dict[n] = ranking
        return result_dict

    ngram_dict = get_cached_ngrams_from_titles_fast(input_path, input_mtime)
    total_input_records = len(input_titles)

    @st.cache_data(show_spinner=False)
    def count_ngram_discarded_records(file_path, file_mtime, ng_rules_tuple):
        if not ng_rules_tuple:
            return 0
        titles = load_filtered_titles(file_path, file_mtime)
        disc_cnt = 0
        for title in titles:
            if any(pattern in title for pattern in ng_rules_tuple):
                disc_cnt += 1
        return disc_cnt

    ngram_discarded_records = count_ngram_discarded_records(input_path, input_mtime, tuple(sorted(list(ngram_ng))))
    ngram_remaining_records = total_input_records - ngram_discarded_records
    ngram_reduction_rate = (ngram_discarded_records / max(1, total_input_records))

    st.subheader("N-Gramルールによるレコード絞り込み進捗")
    ng_c1, ng_c2, ng_c3, ng_c4 = st.columns(4)
    with ng_c1:
        st.metric("About通過後レコード数", f"{total_input_records:,} 件")
    with ng_c2:
        st.metric("N-Gram除外対象数", f"{ngram_discarded_records:,} 件", delta=f"-{ngram_reduction_rate:.1%}", delta_color="inverse")
    with ng_c3:
        st.metric("本工程通過残存レコード", f"{ngram_remaining_records:,} 件", delta=f"{ngram_remaining_records/max(1,total_input_records):.1%}")
    with ng_c4:
        st.metric("本工程での絞り込み率", f"{ngram_reduction_rate:.1%} 削減")

    with st.expander(f"現在の N-Gram NG / OK 登録ルール (NG: {len(ngram_ng)} 件 / OK: {len(ngram_ok)} 件)", expanded=False):
        cn_manage_ng, cn_manage_ok = st.columns(2)
        with cn_manage_ng:
            st.markdown(f"### 除外(NG) N-gram パターン ({len(ngram_ng)} 件)")
            if ngram_ng:
                n_ng_sorted = sorted(list(ngram_ng))
                try:
                    selected_n_ng_pills = st.pills("選択して削除するパターンをクリック:", options=n_ng_sorted, selection_mode="multi", key="pills_ngram_ng")
                except AttributeError:
                    selected_n_ng_pills = st.multiselect("削除するパターンを選択:", options=n_ng_sorted, key="ms_ngram_ng_fallback")

                if st.button("選択パターンの NG ルールからの解除", key="btn_del_n_ng_pills", type="primary", use_container_width=True):
                    if selected_n_ng_pills:
                        ngram_ng.difference_update(selected_n_ng_pills)
                        st.session_state["ngram_view_ver"] += 1
                        st.cache_data.clear()
                        st.success(f"{len(selected_n_ng_pills)} 件のパターンを NG ルールから削除しました。")
                        st.rerun()
                    else:
                        st.warning("解除するパターンが選択されていません。")
            else:
                st.info("NG N-gram ルールは現在空です。")

        with cn_manage_ok:
            st.markdown(f"### 保持(OK) N-gram パターン ({len(ngram_ok)} 件)")
            if ngram_ok:
                n_ok_sorted = sorted(list(ngram_ok))
                try:
                    selected_n_ok_pills = st.pills("選択して削除するパターンをクリック:", options=n_ok_sorted, selection_mode="multi", key="pills_ngram_ok")
                except AttributeError:
                    selected_n_ok_pills = st.multiselect("削除するパターンを選択:", options=n_ok_sorted, key="ms_ngram_ok_fallback")

                if st.button("選択パターンの OK ルールからの解除", key="btn_del_n_ok_pills", type="primary", use_container_width=True):
                    if selected_n_ok_pills:
                        ngram_ok.difference_update(selected_n_ok_pills)
                        st.session_state["ngram_view_ver"] += 1
                        st.cache_data.clear()
                        st.success(f"{len(selected_n_ok_pills)} 件のパターンを OK ルールから削除しました。")
                        st.rerun()
                    else:
                        st.warning("解除するパターンが選択されていません。")
            else:
                st.info("OK N-gram ルールは現在空です。")

    @st.cache_data(show_spinner=False)
    def get_cached_active_titles(file_path, file_mtime, ng_rules_tuple, ok_rules_tuple=None):
        titles = load_filtered_titles(file_path, file_mtime)
        res = []
        for t in titles:
            if not t:
                continue
            if ng_rules_tuple and any(ng in t for ng in ng_rules_tuple):
                continue
            if ok_rules_tuple and any(ok in t for ok in ok_rules_tuple):
                continue
            res.append(t)
        return res

    active_titles = get_cached_active_titles(
        input_path, 
        input_mtime, 
        tuple(sorted(list(ngram_ng))),
        tuple(sorted(list(ngram_ok)))
    )

    def get_parent_rule(word: str, ng_set: set, ok_set: set) -> tuple:
        for ng in sorted(list(ng_set), key=len):
            if len(ng) < len(word) and ng in word:
                return "NG", ng
        for ok in sorted(list(ok_set), key=len):
            if len(ok) < len(word) and ok in word:
                return "OK", ok
        return None, None

    n_options = [
        "2文字 (Bi-gram)", 
        "3文字 (Tri-gram)", 
        "4文字 (Tetra-gram)", 
        "5文字 (Penta-gram)", 
        "6文字 (Hexa-gram)", 
        "7文字 (Hepta-gram)", 
        "8文字 (Octa-gram)", 
        "9文字 (Nona-gram)"
    ]
    
    selected_n_str = st.radio("分析対象の N-gram (文字数) の選択:", options=n_options, horizontal=True, key="selected_n_gram_radio")
    n_val = int(selected_n_str.split("文字")[0])

    items_for_n = ngram_dict.get(n_val, [])

    if "c_mode_ngram_shared" not in st.session_state:
        st.session_state["c_mode_ngram_shared"] = "NGに設定"

    col_n_opt1, col_n_opt2 = st.columns([3, 2])
    with col_n_opt1:
        v_mode_n = st.radio(
            "表示オプション:", 
            options=["すべて表示", "未判定のみ", "NGのみ", "OKのみ"], 
            horizontal=True,
            key="v_mode_ngram_shared"
        )
        is_unclassified_n_mode = (v_mode_n == "未判定のみ")
        hide_zero_ngram = st.checkbox(
            "残存未判定件数が 0 件の N-Gram パターンを非表示にする", 
            value=True, 
            disabled=not is_unclassified_n_mode,
            key="chk_hide_zero_ngram_shared"
        )
    with col_n_opt2:
        q_ngram = st.text_input("N-Gram 検索:", key="q_ngram_shared")

    st.caption("N-gram 判定モード切替 (ショートカット: Q / W / E キー):")
    cn_m1, cn_m2, cn_m3 = st.columns(3)
    
    n_btn1_t = "primary" if st.session_state["c_mode_ngram_shared"] == "NGに設定" else "secondary"
    n_btn2_t = "primary" if st.session_state["c_mode_ngram_shared"] == "OKに設定" else "secondary"
    n_btn3_t = "primary" if st.session_state["c_mode_ngram_shared"] == "未判定に戻す" else "secondary"

    bn1 = cn_m1.button("【 Q 】 NG設定モード", key="btn_mq_n_shared", use_container_width=True, type=n_btn1_t)
    bn2 = cn_m2.button("【 W 】 OK設定モード", key="btn_mw_n_shared", use_container_width=True, type=n_btn2_t)
    bn3 = cn_m3.button("【 E 】 未判定リセット", key="btn_me_n_shared", use_container_width=True, type=n_btn3_t)

    if hotkeys:
        if hotkeys.pressed("mode_ng"):
            st.session_state["c_mode_ngram_shared"] = "NGに設定"
            st.rerun()
        elif hotkeys.pressed("mode_ok"):
            st.session_state["c_mode_ngram_shared"] = "OKに設定"
            st.rerun()
        elif hotkeys.pressed("mode_reset"):
            st.session_state["c_mode_ngram_shared"] = "未判定に戻す"
            st.rerun()

    if bn1:
        st.session_state["c_mode_ngram_shared"] = "NGに設定"
        st.rerun()
    if bn2:
        st.session_state["c_mode_ngram_shared"] = "OKに設定"
        st.rerun()
    if bn3:
        st.session_state["c_mode_ngram_shared"] = "未判定に戻す"
        st.rerun()

    c_mode_n = st.session_state["c_mode_ngram_shared"]

    if c_mode_n == "NGに設定":
        st.error("【現在の設定モード: NG (除外)】 (ショートカット: Q)")
    elif c_mode_n == "OKに設定":
        st.success("【現在の設定モード: OK (保持)】 (ショートカット: W)")
    elif c_mode_n == "未判定に戻す":
        st.info("【現在の設定モード: 未判定リセット】 (ショートカット: E)")

    filtered_items = items_for_n
    if v_mode_n == "未判定のみ":
        filtered_items = [
            (w, c, s) for w, c, s in filtered_items 
            if w not in ngram_ng and w not in ngram_ok and get_parent_rule(w, ngram_ng, ngram_ok)[0] is None
        ]
    elif v_mode_n == "NGのみ":
        filtered_items = [
            (w, c, s) for w, c, s in filtered_items 
            if w in ngram_ng or get_parent_rule(w, ngram_ng, ngram_ok)[0] == "NG"
        ]
    elif v_mode_n == "OKのみ":
        filtered_items = [
            (w, c, s) for w, c, s in filtered_items 
            if w in ngram_ok or get_parent_rule(w, ngram_ng, ngram_ok)[0] == "OK"
        ]

    if q_ngram:
        parts = [p.strip() for p in re.split(r'\s+', q_ngram.replace('　', ' ')) if p.strip()]
        inc_words = [p.lower() for p in parts if not p.startswith('-')]
        exc_words = [p[1:].lower() for p in parts if p.startswith('-') and len(p) > 1]
        
        res_l = []
        for w, c, s in filtered_items:
            w_l = w.lower()
            if all(i in w_l for i in inc_words) and not any(e in w_l for e in exc_words):
                res_l.append((w, c, s))
        filtered_items = res_l

    @st.cache_data(show_spinner=False)
    def get_cached_n_samples_map(active_titles_tuple, target_words_tuple):
        target_words_set = set(target_words_tuple)
        samples_map = defaultdict(list)
        for t in active_titles_tuple:
            clean_t = clean_title_text(t)
            for w in target_words_set:
                if w in clean_t:
                    samples_map[w].append(t)
        return samples_map

    target_words_tuple = tuple(w for w, c, s in filtered_items)
    active_n_samples_map = get_cached_n_samples_map(tuple(active_titles), target_words_tuple)

    if is_unclassified_n_mode and hide_zero_ngram:
        filtered_items = [
            (w, c, s) for w, c, s in filtered_items 
            if len(active_n_samples_map.get(w, [])) > 0 or w in ngram_ng or w in ngram_ok
        ]

    if f"draft_n_{n_val}_changes" not in st.session_state:
        st.session_state[f"draft_n_{n_val}_changes"] = {}
    draft_n = st.session_state[f"draft_n_{n_val}_changes"]

    cn_hdr1, cn_hdr2 = st.columns([3, 2])
    with cn_hdr1:
        st.markdown(f"N={n_val} パターン一覧 (該当: **{len(filtered_items)}** 件)")
    with cn_hdr2:
        draft_n_cnt = len(draft_n)
        btn_n_apply_label = f"N={n_val} 仮設定 ({draft_n_cnt} 件) の一括適用" if draft_n_cnt > 0 else f"N={n_val} 判定の一括適用"
        if st.button(btn_n_apply_label, key=f"btn_apply_n_{n_val}", type="primary" if draft_n_cnt > 0 else "secondary", use_container_width=True):
            if draft_n:
                for w, status in draft_n.items():
                    if status == "NG":
                        ngram_ng.add(w)
                        ngram_ok.discard(w)
                    elif status == "OK":
                        ngram_ok.add(w)
                        ngram_ng.discard(w)
                    elif status == "RESET":
                        ngram_ng.discard(w)
                        ngram_ok.discard(w)
                draft_n.clear()
                st.session_state["ngram_view_ver"] += 1
                st.cache_data.clear()
                st.success(f"N={n_val} の判別結果をルールへ適用しました。")
                st.rerun()
            else:
                st.info("現在仮選択中のパターンはありません。")

    # 汎用ピルボードコンポーネント呼出
    render_pill_board(
        items=filtered_items,
        active_samples_map=active_n_samples_map,
        current_ng=ngram_ng,
        current_ok=ngram_ok,
        draft_dict=draft_n,
        click_action_mode=c_mode_n,
        page_session_key=f"ngram_page_n_{n_val}",
        parent_rule_func=lambda w: get_parent_rule(w, ngram_ng, ngram_ok)
    )

    def build_expanded_ngram_rules(ng_set, ok_set, all_ngram_dict):
        final_dict = {}
        for w in ng_set: final_dict[w] = "NG"
        for w in ok_set: final_dict[w] = "OK"

        for n_val, items in all_ngram_dict.items():
            for word, count, _ in items:
                if word in final_dict:
                    continue
                p_type, p_word = get_parent_rule(word, ng_set, ok_set)
                if p_type:
                    final_dict[word] = p_type
        return final_dict

    st.write("---")
    col_n1, col_n2, col_n3 = st.columns([2, 2, 1])
    with col_n1:
        if st.button("N-Gram ルールを保存する", type="primary", use_container_width=True):
            save_dict = build_expanded_ngram_rules(ngram_ng, ngram_ok, ngram_dict)
            safe_save_json(save_dict, ngram_rules_path)
            st.success(f"N-Gram ルールを保存しました (全 {len(save_dict):,} ルール)。")

    with col_n2:
        if st.button("N-Gram フィルタを実行する", type="primary", use_container_width=True):
            save_dict = build_expanded_ngram_rules(ngram_ng, ngram_ok, ngram_dict)
            safe_save_json(save_dict, ngram_rules_path)

            passed, disc = run_ngram_filter(input_path, ngram_rules_path, ngram_filtered_path, f"{data_dir}/discarded_ngram.csv")
            st.success(f"N-Gram フィルタリング完了: 通過 {passed:,} 件 / 除外 {disc:,} 件 (除外ログ: {data_dir}/discarded_ngram.csv)")

    with col_n3:
        with st.popover("ルール全初期化", help="N-Gramルールを初期化"):
            st.warning("N-Gram ルール (`ngram_rules.json`) を全初期化しますか？")
            st.caption("登録済みの全 N-gram NG / OK パターンが消去されます。")
            if st.button("確定して初期化を実行", type="primary", use_container_width=True, key="btn_confirm_reset_ngram"):
                st.session_state["edited_ngram_ng"] = set()
                st.session_state["edited_ngram_ok"] = set()
                for key in list(st.session_state.keys()):
                    if key.startswith("draft_n_"):
                        st.session_state[key] = {}
                safe_save_json({}, ngram_rules_path)

                for p_rm in [ngram_filtered_path, f"{data_dir}/discarded_ngram.csv"]:
                    if os.path.exists(p_rm):
                        try:
                            os.remove(p_rm)
                        except Exception:
                            pass
                st.cache_data.clear()
                st.session_state["ngram_view_ver"] += 1
                st.success("N-Gram ルールおよびフィルタ結果を初期化しました。")
                st.rerun()
