# -*- coding: utf-8 -*-
import streamlit as st
import pandas as pd
import json
import os
import re
import urllib.parse
import time
from collections import Counter
import streamlit.components.v1 as components

# 各処理モジュールのインポート
from modules.importer import import_existing_assets, get_import_status
from modules.rule_filter import run_about_filter, run_suffix_filter
from modules.ngram_sorter import run_ngram_analysis, run_data_split
from modules.llm_pipeline import run_llm_judgment_generator, run_merge_data
from modules.metadata_enricher import (
    run_metadata_enrichment_background, 
    merge_enriched_metadata, 
    GENRES, 
    INSTRUMENTS
)

# ==========================================
# 0. 基本設定とパス定義
# ==========================================
st.set_page_config(layout="wide", page_title="楽譜データクレンジング・ポータル")

PORTAL_DIR = "integrated_portal"
RULES_DIR = f"{PORTAL_DIR}/rules"
DATA_DIR = f"{PORTAL_DIR}/data"
STEPS_DIR = f"{PORTAL_DIR}/pipeline_steps"

# 主要ファイルパス
PATH_TARGET_URIS = f"{STEPS_DIR}/01_data_collection/target_uris.csv"
PATH_RAW_METADATA = f"{STEPS_DIR}/01_data_collection/raw_metadata.jsonl"

PATH_ABOUT_RULES = f"{RULES_DIR}/about_rules.json"
PATH_SUFFIX_RULES = f"{RULES_DIR}/suffix_rules.json"
PATH_OK_LIST = f"{RULES_DIR}/ok_word_list.txt"
PATH_NG_LIST = f"{RULES_DIR}/ng_word_list.txt"

PATH_ABOUT_RANKING = f"{STEPS_DIR}/02_rule_based_filtering/about_ranking.csv"
PATH_ABOUT_FILTERED = f"{STEPS_DIR}/02_rule_based_filtering/about_filtered.jsonl"
PATH_DISCARDED_ABOUT = f"{STEPS_DIR}/02_rule_based_filtering/discarded_about.csv"
PATH_SUFFIX_RANKING = f"{STEPS_DIR}/02_rule_based_filtering/suffix_ranking.csv"
PATH_SUFFIX_SAMPLES = f"{STEPS_DIR}/02_rule_based_filtering/suffix_samples.json"
PATH_DISCARDED_SUFFIX = f"{STEPS_DIR}/02_rule_based_filtering/discarded_suffix.csv"

PATH_SUFFIX_FILTERED = f"{STEPS_DIR}/03_hybrid_classification/suffix_filtered.jsonl"
PATH_NGRAM_RANKING = f"{STEPS_DIR}/03_hybrid_classification/ngram_ranking.csv"
PATH_NGRAM_SAMPLES = f"{STEPS_DIR}/03_hybrid_classification/ngram_samples.json"
PATH_CONFIRMED_OK = f"{STEPS_DIR}/03_hybrid_classification/confirmed_ok.jsonl"
PATH_CONFIRMED_NG = f"{STEPS_DIR}/03_hybrid_classification/confirmed_ng.jsonl"
PATH_TARGET_FOR_LLM = f"{STEPS_DIR}/03_hybrid_classification/target_for_llm.jsonl"
PATH_LLM_JUDGMENTS = f"{STEPS_DIR}/03_hybrid_classification/llm_judgments.jsonl"
PATH_MERGED_FOR_VERIFICATION = f"{STEPS_DIR}/03_hybrid_classification/merged_for_verification.jsonl"

PATH_ENRICHED_METADATA = f"{STEPS_DIR}/03_hybrid_classification/enriched_metadata.jsonl"
PATH_METADATA_PROGRESS = f"{DATA_DIR}/metadata_progress.json"

PATH_CLEANED_JSONL = f"{DATA_DIR}/classical_scores_cleaned.jsonl"
PATH_CLEANED_CSV = f"{DATA_DIR}/classical_scores_cleaned.csv"
PATH_VOCAB_RANKING = f"{DATA_DIR}/vocab_ranking_scores.csv"

PATH_EXPORT_DIR = "docs/score_search"
PATH_EXPORT_JSON = f"{PATH_EXPORT_DIR}/scores_data.json"

# ==========================================
# ヘルパー関数
# ==========================================
def check_file_exists_and_size(path):
    if os.path.exists(path):
        size_kb = os.path.getsize(path) / 1024
        return True, f"存在する ({size_kb:.1f} KB)"
    return False, "未生成"

def count_lines(path):
    if not os.path.exists(path):
        return 0
    try:
        with open(path, 'r', encoding='utf-8', errors='replace') as f:
            return sum(1 for _ in f)
    except Exception:
        return 0

def load_text_list_to_set(path):
    if os.path.exists(path):
        with open(path, 'r', encoding='utf-8') as f:
            return set([line.strip() for line in f if line.strip()])
    return set()

def save_set_to_text_list(path, word_set):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    words = sorted(list(word_set))
    with open(path, 'w', encoding='utf-8') as f:
        for w in words:
            f.write(f"{w}\n")
    return len(words)

def make_google_link(word):
    word_str = str(word)
    if word_str.startswith("http"):
        # URLから最後尾のキーワード部分を抽出してデコード
        try:
            parsed = urllib.parse.urlparse(word_str)
            path_parts = [p for p in parsed.path.split('/') if p]
            keyword = urllib.parse.unquote(path_parts[-1]) if path_parts else word_str
        except Exception:
            keyword = word_str
        
        query = urllib.parse.quote(f"{keyword} とは")
        return f"[[🔍]](https://www.google.com/search?q={query})"
    
    query = urllib.parse.quote(f"{word_str} とは")
    return f"[[🔍]](https://www.google.com/search?q={query})"

def get_japan_search_link(item):
    source_info = item.get("https://jpsearch.go.jp/term/property#sourceInfo")
    if isinstance(source_info, dict):
        link = source_info.get("schema:relatedLink")
        if link:
            return link
    item_id = item.get("@id", item.get("id"))
    if item_id and "jpsearch.go.jp/data/" in item_id:
        return item_id.replace("jpsearch.go.jp/data/", "jpsearch.go.jp/item/")
    return None

def render_pagination(total_pages, current_page, key_prefix):
    if total_pages <= 1:
        return current_page

    pages_to_show = []
    if total_pages <= 7:
        pages_to_show = list(range(1, total_pages + 1))
    else:
        pages_to_show.append(1)
        if current_page > 3:
            pages_to_show.append("...")
        elif current_page == 3:
            pages_to_show.append(2)
            
        start = max(2, current_page - 1)
        if current_page == 1 or current_page == 2:
            start = 2
        
        end = min(total_pages - 1, current_page + 1)
        if current_page == total_pages or current_page == total_pages - 1:
            end = total_pages - 1
            
        for p in range(start, end + 1):
            if p not in pages_to_show:
                pages_to_show.append(p)
                
        if current_page < total_pages - 2:
            pages_to_show.append("...")
        elif current_page == total_pages - 2:
            if total_pages - 1 not in pages_to_show:
                pages_to_show.append(total_pages - 1)
                
        if total_pages not in pages_to_show:
            pages_to_show.append(total_pages)

    cols_count = len(pages_to_show) + 2
    cols = st.columns(cols_count)
    
    new_page = current_page
    
    with cols[0]:
        if st.button("◀", key=f"{key_prefix}_prev", disabled=(current_page <= 1), use_container_width=True):
            new_page = current_page - 1
            
    for i, p in enumerate(pages_to_show):
        with cols[i + 1]:
            if p == "...":
                st.markdown("<div style='text-align: center; line-height: 2.2rem; color: gray;'>...</div>", unsafe_allow_html=True)
            else:
                is_current = (p == current_page)
                btn_type = "primary" if is_current else "secondary"
                if st.button(str(p), key=f"{key_prefix}_page_{p}", type=btn_type, use_container_width=True):
                    new_page = p
                    
    with cols[-1]:
        if st.button("▶", key=f"{key_prefix}_next", disabled=(current_page >= total_pages), use_container_width=True):
            new_page = current_page + 1
            
    if new_page != current_page:
        st.session_state["verification_page"] = new_page
        st.rerun()
        
    return new_page

def inject_save_shortcut():
    # 画面上には表示しない隠し要素として親DOMにキーボードリスナーを注入
    components.html(
        """
        <script>
        const doc = window.parent.document;
        // 重複登録を防ぐため、既存のリスナーがあれば一度削除
        if (window.parent.__saveShortcutListener) {
            doc.removeEventListener('keydown', window.parent.__saveShortcutListener);
        }
        
        window.parent.__saveShortcutListener = function(e) {
            // Cmd+S (Mac) または Ctrl+S (Windows/Linux)
            if ((e.metaKey || e.ctrlKey) && e.key === 's') {
                e.preventDefault();
                
                // "保存" または "💾" という文字列を含むStreamlitボタンを探してクリック
                const buttons = doc.querySelectorAll('button');
                let clicked = false;
                for (const btn of buttons) {
                    if (btn.textContent.includes('保存') || btn.textContent.includes('💾')) {
                        btn.click();
                        clicked = true;
                        break;
                    }
                }
                if (clicked) {
                    console.log("Portal Shortcut: Save triggered successfully.");
                }
            }
        };
        
        doc.addEventListener('keydown', window.parent.__saveShortcutListener);
        </script>
        """,
        height=0,
        width=0
    )

def inject_pagination_shortcut():
    # 画面上には表示しない隠し要素として親DOMにキーボードリスナーを注入
    components.html(
        """
        <script>
        const doc = window.parent.document;
        // 重複登録を防ぐため、既存のリスナーがあれば一度削除
        if (window.parent.__paginationShortcutListener) {
            doc.removeEventListener('keydown', window.parent.__paginationShortcutListener);
        }
        
        window.parent.__paginationShortcutListener = function(e) {
            // アクティブな要素が入力フィールド（input, textarea, select）の場合はショートカットを無視
            const activeEl = doc.activeElement;
            if (activeEl && (
                activeEl.tagName === 'INPUT' || 
                activeEl.tagName === 'TEXTAREA' || 
                activeEl.tagName === 'SELECT' || 
                activeEl.isContentEditable
            )) {
                return;
            }

            // Alt (Option) + ArrowRight (次のページ)
            if (e.altKey && e.key === 'ArrowRight') {
                e.preventDefault();
                const buttons = doc.querySelectorAll('button');
                for (const btn of buttons) {
                    if (btn.textContent.includes('次のページ')) {
                        btn.click();
                        console.log("Portal Shortcut: Next page triggered.");
                        break;
                    }
                }
            }
            // Alt (Option) + ArrowLeft (前のページ)
            else if (e.altKey && e.key === 'ArrowLeft') {
                e.preventDefault();
                const buttons = doc.querySelectorAll('button');
                for (const btn of buttons) {
                    if (btn.textContent.includes('前のページ')) {
                        btn.click();
                        console.log("Portal Shortcut: Previous page triggered.");
                        break;
                    }
                }
            }
        };
        
        doc.addEventListener('keydown', window.parent.__paginationShortcutListener);
        </script>
        """,
        height=0,
        width=0
    )

# ==========================================
# メイン画面とナビゲーション
# ==========================================
# ショートカットキーリスナーの有効化
inject_save_shortcut()

st.sidebar.title("古典籍データ判定ポータル")
st.sidebar.caption("楽譜書誌精査システム")

menu_options = [
    "Dashboard",
    "Step 1: データインポート・収集",
    "Step 2-A: Aboutキーワード仕分け",
    "Step 2-B: 末尾語彙仕分け",
    "Step 3: N-gram仕分け",
    "Step 4: LLM自動判定",
    "Step 4-B: 音楽メタデータ付与",
    "Step 5: 最終査読と確定",
    "Step 6: 検索ツールのエクスポート"
]
choice = st.sidebar.radio("工程を選択:", menu_options)

# ==========================================
# Dashboard
# ==========================================
if choice == "Dashboard":
    st.title("パイプライン全体ダッシュボード")
    st.markdown("クレンジングプロセスの全体進捗状況と、各フェーズの中間ファイル件数を可視化します。")
    
    # 既存インポート状況のサマリー
    st.subheader("各ステップの中間ファイル状態")
    
    cols = st.columns(3)
    
    # 収集データ
    with cols[0]:
        st.info("Phase 1: 収集")
        _, meta_status = check_file_exists_and_size(PATH_RAW_METADATA)
        st.metric("収集済み書誌データ", f"{count_lines(PATH_RAW_METADATA)} 件", help=meta_status)
        
    # ルールベース合格データ
    with cols[1]:
        st.warning("Phase 2: ルールベース")
        _, about_status = check_file_exists_and_size(PATH_ABOUT_FILTERED)
        _, suffix_status = check_file_exists_and_size(PATH_SUFFIX_FILTERED)
        st.metric("About フィルタ通過件数", f"{count_lines(PATH_ABOUT_FILTERED)} 件", help=about_status)
        st.metric("末尾 フィルタ通過件数", f"{count_lines(PATH_SUFFIX_FILTERED)} 件", help=suffix_status)
        
    # ハイブリッド分類データ
    with cols[2]:
        st.success("Phase 3: ハイブリッド判定")
        st.metric("N-gram 確定OK件数", f"{count_lines(PATH_CONFIRMED_OK)} 件")
        st.metric("LLM判定対象 (Gray)", f"{count_lines(PATH_TARGET_FOR_LLM)} 件")
        st.metric("LLM判定済み件数", f"{count_lines(PATH_LLM_JUDGMENTS)} 件")
        
    st.divider()
    
    # 成果物の状態
    st.subheader("最終成果物")
    if os.path.exists(PATH_CLEANED_JSONL):
        st.success(f"最終成果物が生成されています: {PATH_CLEANED_JSONL} ({count_lines(PATH_CLEANED_JSONL)}件)")
    else:
        st.info("最終成果物は未確定です。Step 5まで進めて「最終確定」を行ってください。")

# ==========================================
# Step 1: データインポート・収集
# ==========================================
elif choice == "Step 1: データインポート・収集":
    st.title("データのインポートと初期収集")
    st.markdown("以前の作業で作成された既存のデータ・ルールをインポートするか、SPARQL経由で新規データを収集します。")
    
    tab_import, tab_collect = st.tabs(["既存アセットのインポート (推奨)", "ジャパンサーチから新規取得"])
    
    with tab_import:
        st.subheader("既存データ・ルールの安全コピー")
        st.markdown(
            "プロジェクトルートにある `data/` や `fragments/` フォルダから、"
            "収集済みの生データや、人間が仕分けた各種ルールを**コピー（複製）**して新構造に配置します。"
            "\n\n**※元のファイルは一切削除・変更されません。安全です。**"
        )
        
        status = get_import_status()
        import_df_data = []
        for key, s in status.items():
            import_df_data.append({
                "対象アセット": key,
                "元アセットの存在": "あり" if s["source_exists"] else "なし",
                "ポータル内アセットの存在": "移植済み" if s["dest_exists"] else "未移植",
                "ポータル内配置先": s["dest_path"]
            })
            
        st.table(import_df_data)
        
        c1, c2 = st.columns(2)
        with c1:
            if st.button("データをインポートする", type="primary", use_container_width=True):
                with st.spinner("安全コピーを実行中..."):
                    results = import_existing_assets(overwrite=True)
                    st.success("インポート完了！以下のファイルを複製しました。")
                    for r in results:
                        if r["status"] == "imported":
                            st.caption(f"・{r['file']}: コピー成功")
                    time.sleep(1)
                    st.rerun()

    with tab_collect:
        st.subheader("SPARQL ＆ Web APIによる新規取得")
        st.warning("新規に収集を行うと、既存データは上書きされ、API実行に時間がかかります。")
        st.button("SPARQLクエリを実行してURI一覧を取得 (URIListMaker)", disabled=True)
        st.button("詳細メタデータの一括グラフ構築 (BuildMetadata)", disabled=True)

# ==========================================
# Step 2-A: Aboutキーワード仕分け
# ==========================================
elif choice == "Step 2-A: Aboutキーワード仕分け":
    st.title("Aboutキーワード仕分け")
    st.markdown("`schema:about` のキーワード（URIや語彙）に基づいて、楽譜であるレコード（ホワイト）とノイズ（ブラック）を判定します。")
    
    # 前提データチェック
    if not os.path.exists(PATH_RAW_METADATA):
        st.warning("前提データ (raw_metadata.jsonl) が存在しません。まず Step 1 でインポートを行ってください。")
        st.stop()
        
    PATH_ABOUT_SAMPLES = f"{STEPS_DIR}/02_rule_based_filtering/about_samples.json"

    # 頻出CSVの自動生成（なければ）
    if not os.path.exists(PATH_ABOUT_RANKING) or not os.path.exists(PATH_ABOUT_SAMPLES):
        st.info("Aboutキーワードとサンプルを初回集計しています...")
        # 簡易的に about抽出.py のロジックを実行
        from collections import Counter, defaultdict
        all_keywords = []
        sample_map = defaultdict(list)
        MAX_SAMPLES = 20
        with open(PATH_RAW_METADATA, 'r', encoding='utf-8') as f:
            for line in f:
                try:
                    data = json.loads(line)
                    label = data.get('rdfs:label')
                    name = data.get('schema:name')
                    title = str(label) if label else (str(name) if name else "No Title")
                    
                    about_data = data.get('schema:about')
                    if about_data:
                        # 簡易抽出
                        def extract_robust(obj):
                            vals = []
                            if isinstance(obj, str): vals.append(obj)
                            elif isinstance(obj, list):
                                for item in obj: vals.extend(extract_robust(item))
                            elif isinstance(obj, dict):
                                if '@id' in obj: vals.append(obj['@id'])
                                for k in ['name', 'schema:name', 'rdfs:label']:
                                    if k in obj: vals.extend(extract_robust(obj[k]))
                            return vals
                        keywords = extract_robust(about_data)
                        all_keywords.extend(keywords)
                        
                        # タイトルを紐付け
                        for kw in set(keywords):
                            if len(sample_map[kw]) < MAX_SAMPLES:
                                if title not in sample_map[kw]:
                                    sample_map[kw].append(title)
                except:
                    continue
        counter = Counter(all_keywords)
        results = [{"Rank": i+1, "Word": word, "Count": count} for i, (word, count) in enumerate(counter.most_common())]
        os.makedirs(os.path.dirname(PATH_ABOUT_RANKING), exist_ok=True)
        pd.DataFrame(results).to_csv(PATH_ABOUT_RANKING, index=False, encoding='utf-8-sig')
        
        # サンプルデータの保存
        with open(PATH_ABOUT_SAMPLES, 'w', encoding='utf-8') as f:
            json.dump(sample_map, f, ensure_ascii=False, indent=2)
            
        st.success("Aboutキーワードとサンプルの集計が完了しました！")
        st.rerun()

    # サンプルデータのロード
    if "about_samples" not in st.session_state:
        if os.path.exists(PATH_ABOUT_SAMPLES):
            with open(PATH_ABOUT_SAMPLES, 'r', encoding='utf-8') as f:
                st.session_state["about_samples"] = json.load(f)
        else:
            st.session_state["about_samples"] = {}

    # セッションルール初期化
    if "about_rules_loaded" not in st.session_state:
        rules_data = {"NOISE_PATTERNS": [], "STRONG_KEYWORDS": []}
        if os.path.exists(PATH_ABOUT_RULES):
            with open(PATH_ABOUT_RULES, 'r', encoding='utf-8') as f:
                rules_data = json.load(f)
        st.session_state["edited_noise"] = set(rules_data.get("NOISE_PATTERNS", []))
        st.session_state["edited_strong"] = set(rules_data.get("STRONG_KEYWORDS", []))
        st.session_state["about_rules_loaded"] = True
        st.session_state["about_view_version"] = 0

    # UI定義
    about_df = pd.read_csv(PATH_ABOUT_RANKING)
    
    with st.sidebar:
        st.header("設定")
        list_type = st.radio("編集対象のリスト", ["ブラックリスト (除外)", "ホワイトリスト (残す)"])
        st.session_state["current_list_type"] = list_type
        
        hide_classified = st.checkbox("分類済みの語を非表示", value=True)
        max_items = st.number_input("表示件数の上限", min_value=100, max_value=5000, value=500)
        
        current_selection = (
            st.session_state["edited_noise"] 
            if list_type == "ブラックリスト (除外)" 
            else st.session_state["edited_strong"]
        )
        
        st.divider()
        st.metric("選択中件数", len(current_selection))
        
        if st.button("ルールを保存して適用", type="primary", use_container_width=True):
            # 保存
            rules_data = {
                "NOISE_PATTERNS": sorted(list(st.session_state["edited_noise"])),
                "STRONG_KEYWORDS": sorted(list(st.session_state["edited_strong"]))
            }
            with open(PATH_ABOUT_RULES, 'w', encoding='utf-8') as f:
                json.dump(rules_data, f, ensure_ascii=False, indent=2)
                
            # フィルタの適用 (about_filter.py相当の実行)
            with st.spinner("Aboutフィルタを適用し、合格データを生成中..."):
                k_cnt, d_cnt = run_about_filter(
                    input_jsonl=PATH_RAW_METADATA,
                    output_jsonl=PATH_ABOUT_FILTERED,
                    output_discarded_csv=PATH_DISCARDED_ABOUT,
                    output_suffix_csv=PATH_SUFFIX_RANKING,
                    output_samples_json=PATH_SUFFIX_SAMPLES,
                    rules_file=PATH_ABOUT_RULES
                )
                # 後続のStep 3用の中間ファイルを「要更新」にするため、古いN-gramファイルを削除（手戻り対策）
                if os.path.exists(PATH_NGRAM_RANKING):
                    os.remove(PATH_NGRAM_RANKING)
                st.success(f"適用完了: 合格 {k_cnt} 件 / 除外 {d_cnt} 件")
                st.session_state["about_view_version"] += 1
                time.sleep(4)
                st.rerun()

    # メイン画面の検索と仕分け
    search_query = st.text_input("キーワード検索 (部分一致)")
    df_display = about_df
    
    # 既知ルールに含まれるものは、別アプローチ（ルールファイルは温存・UI非表示）に基づき表示制御
    # ただし、現在選択中のリストに含まれているものはチェック状態でUIに表示してもよい。
    # ユーザーが「分類済みを非表示」をONにした場合は、両方のセット（OK/NG）の合計に含まれるものを隠す。
    all_known_rules = st.session_state["edited_noise"] | st.session_state["edited_strong"]
    
    if hide_classified:
        # 分類済みのものは非表示にする
        df_display = df_display[~df_display["Word"].isin(all_known_rules)]
        
    if search_query:
        df_display = df_display[df_display["Word"].astype(str).str.contains(search_query, na=False, case=False)]
        
    df_view = df_display.head(max_items)
    
    # グリッド表示
    cols = st.columns(3)
    view_ver = st.session_state["about_view_version"]
    
    def toggle_about_word(word, unique_key):
        is_checked = st.session_state[unique_key]
        sel_set = (
            st.session_state["edited_noise"] 
            if st.session_state["current_list_type"] == "ブラックリスト (除外)" 
            else st.session_state["edited_strong"]
        )
        opp_set = (
            st.session_state["edited_strong"] 
            if st.session_state["current_list_type"] == "ブラックリスト (除外)" 
            else st.session_state["edited_noise"]
        )
        if is_checked:
            sel_set.add(word)
            if word in opp_set: opp_set.remove(word)
        else:
            if word in sel_set: sel_set.remove(word)

    for idx, (_, row) in enumerate(df_view.iterrows()):
        word = row["Word"]
        count = row["Count"]
        
        is_checked = word in current_selection
        col = cols[idx % 3]
        
        # Google検索リンク
        search_link = make_google_link(word)
        
        display_word = str(word)
        if len(display_word) > 25 and display_word.startswith("http"):
            display_word = "..." + display_word[-22:]
            
        label = f"**{display_word}** ({count}) {search_link}"
        unique_key = f"chk_about_{word}_v{view_ver}"
        
        # ツールチップの構築（はてなアイコンにマウスオーバー）
        example_list = st.session_state["about_samples"].get(word, [])
        tooltip = "【資料例】\n" + "\n".join([f"・{t}" for t in example_list]) if example_list else "サンプルなし"
        
        col.checkbox(
            label,
            value=is_checked,
            key=unique_key,
            help=tooltip,
            on_change=toggle_about_word,
            args=(word, unique_key)
        )

# ==========================================
# Step 2-B: 末尾語彙仕分け
# ==========================================
elif choice == "Step 2-B: 末尾語彙仕分け":
    st.title("末尾語彙(〜譜)仕分け")
    st.markdown("データに含まれる「〇〇譜」という末尾語彙を検出し、そのうち楽譜ではないもの（家譜、年譜など）を除外パターンに登録します。")
    
    # 前提データチェック
    if not os.path.exists(PATH_ABOUT_FILTERED):
        st.warning("前提データ (about_filtered.jsonl) が存在しません。まず Step 2-A を完了してください。")
        st.stop()
        
    if not os.path.exists(PATH_SUFFIX_RANKING):
        st.warning("集計データ (suffix_ranking.csv) が存在しません。まず Step 2-A の「ルールを保存して適用」を実行してください。")
        st.stop()

    # ルール初期化
    if "suffix_rules_loaded" not in st.session_state:
        rules = []
        if os.path.exists(PATH_SUFFIX_RULES):
            with open(PATH_SUFFIX_RULES, 'r', encoding='utf-8') as f:
                rules = json.load(f).get("NOISE_PATTERNS", [])
        st.session_state["suffix_ng_set"] = set(rules)
        st.session_state["suffix_rules_loaded"] = True
        st.session_state["suffix_view_version"] = 0

    # サンプルデータのロード
    with open(PATH_SUFFIX_SAMPLES, 'r', encoding='utf-8') as f:
        sample_map = json.load(f)

    # UI定義
    with st.sidebar:
        st.header("設定")
        max_items = st.number_input("表示件数の上限", min_value=100, max_value=2000, value=500)
        hide_redundant = st.checkbox("親パターン選択済みの語を非表示", value=True)
        
        st.divider()
        st.metric("NG登録件数", len(st.session_state["suffix_ng_set"]))
        
        if st.button("ルールを保存して適用", type="primary", use_container_width=True):
            # 保存
            rules_data = {"NOISE_PATTERNS": sorted(list(st.session_state["suffix_ng_set"]))}
            with open(PATH_SUFFIX_RULES, 'w', encoding='utf-8') as f:
                json.dump(rules_data, f, ensure_ascii=False, indent=2)
                
            # フィルタ適用 (suffix_filter.py相当)
            with st.spinner("接尾辞フィルタを適用し、合格データを生成中..."):
                k_cnt, d_cnt = run_suffix_filter(
                    input_jsonl=PATH_ABOUT_FILTERED,
                    output_jsonl=PATH_SUFFIX_FILTERED,
                    output_discarded_csv=PATH_DISCARDED_SUFFIX,
                    rules_file=PATH_SUFFIX_RULES
                )
                # 後続の中間ファイルを「要更新」にするため古いN-gramを削除
                if os.path.exists(PATH_NGRAM_RANKING):
                    os.remove(PATH_NGRAM_RANKING)
                st.success(f"適用完了: 合格 {k_cnt} 件 / 除外 {d_cnt} 件")
                st.session_state["suffix_view_version"] += 1
                time.sleep(4)
                st.rerun()

    # CSVの読み込みとパース
    raw_df = pd.read_csv(PATH_SUFFIX_RANKING)
    parsed_data = {}
    target_cols = [f"Last{i}" for i in range(2, 10)]
    for key in target_cols:
        found_col = next((c for c in raw_df.columns if key in c), None)
        if not found_col: continue
        rows = []
        for val in raw_df[found_col].dropna():
            if not isinstance(val, str) or not val: continue
            match = re.match(r"(.+) \((\d+)\)", val)
            if match:
                rows.append({"Word": match.group(1), "Count": int(match.group(2))})
        if rows:
            parsed_data[key] = pd.DataFrame(rows).sort_values("Count", ascending=False)

    # タブ表示
    tab_keys = [f"Last{i}" for i in range(2, 10)]
    tabs = st.tabs([f"Last{i} ({i-1}文字+譜)" for i in range(2, 10)])
    
    current_ng_set = st.session_state["suffix_ng_set"]
    view_ver = st.session_state["suffix_view_version"]

    def toggle_suffix_word(word, unique_key):
        is_checked = st.session_state[unique_key]
        if is_checked:
            st.session_state["suffix_ng_set"].add(word)
        else:
            if word in st.session_state["suffix_ng_set"]:
                st.session_state["suffix_ng_set"].remove(word)

    for tab, key in zip(tabs, tab_keys):
        with tab:
            df = parsed_data.get(key, pd.DataFrame())
            if df.empty:
                st.info("データがありません")
                continue
                
            df_view = df.head(max_items)
            cols = st.columns(4)
            
            # 親・冗長フィルタリング
            visible_items = []
            for _, row in df_view.iterrows():
                word = row["Word"]
                count = row["Count"]
                
                is_checked = word in current_ng_set
                is_disabled = False
                label_prefix = ""
                
                if not is_checked:
                    for parent in current_ng_set:
                        if len(parent) < len(word) and word.endswith(parent):
                            is_disabled = True
                            label_prefix = f"⛔({parent}) "
                            break
                            
                if hide_redundant and is_disabled:
                    continue
                    
                visible_items.append((word, count, is_checked, is_disabled, label_prefix))
                
            for idx, (word, count, is_checked, is_disabled, label_prefix) in enumerate(visible_items):
                col = cols[idx % 4]
                
                example_list = sample_map.get(word, [])
                tooltip = "【資料例】\n" + "\n".join([f"・{t}" for t in example_list]) if example_list else "サンプルなし"
                
                search_link = make_google_link(word)
                
                label = f"{label_prefix}**{word}** ({count}) {search_link}"
                unique_key = f"chk_suffix_{key}_{word}_v{view_ver}"
                
                col.checkbox(
                    label,
                    value=is_checked,
                    key=unique_key,
                    disabled=is_disabled,
                    help=tooltip,
                    on_change=toggle_suffix_word,
                    args=(word, unique_key)
                )

# ==========================================
# Step 3: N-gram仕分け
# ==========================================
elif choice == "Step 3: N-gram仕分け":
    st.title("N-gram仕分けとデータ分割")
    st.markdown("資料タイトルから抽出したN-gram（部分文字列）をOK（楽譜関連）とNG（無関係）に仕分け、データを3分類します。")
    
    # 前提データチェック
    if not os.path.exists(PATH_SUFFIX_FILTERED):
        st.warning("前提データ (suffix_filtered.jsonl) が存在しません。まず Step 2-B を完了してください。")
        st.stop()

    # N-gram分析の自動実行（なければ）
    if not os.path.exists(PATH_NGRAM_RANKING):
        st.info("N-gramランキングを自動生成中...")
        run_ngram_analysis(
            input_jsonl=PATH_SUFFIX_FILTERED,
            output_csv=PATH_NGRAM_RANKING,
            output_samples_json=PATH_NGRAM_SAMPLES,
            top_n=200
        )
        st.success("N-gramランキングの生成が完了しました")
        st.rerun()

    # ルール読み込み
    if "ngram_rules_loaded" not in st.session_state:
        st.session_state["ngram_ok_set"] = load_text_list_to_set(PATH_OK_LIST)
        st.session_state["ngram_ng_set"] = load_text_list_to_set(PATH_NG_LIST)
        st.session_state["ngram_rules_loaded"] = True
        st.session_state["ngram_view_version"] = 0

    # UI設定
    with st.sidebar:
        st.header("設定")
        mode = st.radio("クリック時の動作:", ("NG (ノイズ)", "OK (楽譜)"))
        mode_key = "NG" if "NG" in mode else "OK"
        
        hide_redundant = st.checkbox("判定確定済みの語を非表示", value=True)
        
        st.divider()
        if st.button("リストを保存して実行", type="primary", use_container_width=True):
            # 保存
            save_set_to_text_list(PATH_OK_LIST, st.session_state["ngram_ok_set"])
            save_set_to_text_list(PATH_NG_LIST, st.session_state["ngram_ng_set"])
            
            # 3分割実行
            with st.spinner("データを OK/NG/Gray の3つに分割中..."):
                counts = run_data_split(
                    input_jsonl=PATH_SUFFIX_FILTERED,
                    ok_list_path=PATH_OK_LIST,
                    ng_list_path=PATH_NG_LIST,
                    out_ok_jsonl=PATH_CONFIRMED_OK,
                    out_ng_jsonl=PATH_CONFIRMED_NG,
                    out_gray_jsonl=PATH_TARGET_FOR_LLM
                )
                st.success(
                    f"分割完了:\n"
                    f"・確定OK: {counts['ok']} 件\n"
                    f"・確定NG: {counts['ng']} 件\n"
                    f"・LLM判定(Gray): {counts['gray']} 件"
                )
                st.session_state["ngram_view_version"] += 1
                time.sleep(4)
                st.rerun()

        st.divider()
        st.metric("NG登録数", len(st.session_state["ngram_ng_set"]))
        st.metric("OK登録数", len(st.session_state["ngram_ok_set"]))

    # データとサンプルの読み込み
    df = pd.read_csv(PATH_NGRAM_RANKING)
    with open(PATH_NGRAM_SAMPLES, 'r', encoding='utf-8') as f:
        samples_map = json.load(f)

    # 検索窓
    search_query = st.text_input("🔍 N-gramの検索")
    
    configs = [
        {"n": "2", "label": "2文字", "col": "Bi"},
        {"n": "3", "label": "3文字", "col": "Tri"},
        {"n": "4", "label": "4文字", "col": "Tetra"},
        {"n": "5", "label": "5文字", "col": "Penta"},
    ]
    tabs = st.tabs([c["label"] for c in configs])

    current_ng_set = st.session_state["ngram_ng_set"]
    current_ok_set = st.session_state["ngram_ok_set"]
    view_ver = st.session_state["ngram_view_version"]

    def toggle_ngram_word(word, target_mode, unique_key):
        is_checked = st.session_state[unique_key]
        target = st.session_state["ngram_ok_set"] if target_mode == "OK" else st.session_state["ngram_ng_set"]
        opp = st.session_state["ngram_ng_set"] if target_mode == "OK" else st.session_state["ngram_ok_set"]
        if is_checked:
            target.add(word)
            if word in opp: opp.remove(word)
        else:
            if word in target: target.remove(word)

    for conf, tab in zip(configs, tabs):
        with tab:
            col_w = f"{conf['col']}-gram"
            col_c = f"{conf['col']}-Count"
            sub_df = df[[col_w, col_c]].dropna()

            if search_query:
                sub_df = sub_df[sub_df[col_w].astype(str).str.contains(search_query, na=False)]
                display_df = sub_df
            else:
                display_df = sub_df.head(200)

            if display_df.empty:
                st.info("該当なし")
                continue

            cols = st.columns(4)
            n_samples = samples_map.get(conf["n"], {})

            visible_items = []
            for _, row in display_df.iterrows():
                word = str(row[col_w])
                count = int(row[col_c])
                
                is_ng = word in current_ng_set
                is_ok = word in current_ok_set
                
                is_disabled = False
                parent_word = ""
                parent_type = ""
                ex_list = n_samples.get(word, [])

                # 自分が判定されていない場合の「自動競合防止＆ロック」判定
                if not (is_ng or is_ok):
                    # 1. NGリストの親を探す
                    for p in current_ng_set:
                        if len(p) < len(word) and p in word:
                            is_disabled = True
                            parent_word = p
                            parent_type = "NG"
                            break
                    # 2. OKリストの親を探す
                    if not is_disabled:
                        for p in current_ok_set:
                            if len(p) < len(word) and p in word:
                                is_disabled = True
                                parent_word = p
                                parent_type = "OK"
                                break
                    # 3. 資料レベルの自動除外判定
                    if not is_disabled and ex_list:
                        all_discarded = True
                        blocked_by = set()
                        for title in ex_list:
                            title_has_ng = False
                            for ng in current_ng_set:
                                if ng in title:
                                    title_has_ng = True
                                    blocked_by.add(ng)
                                    break
                            if not title_has_ng:
                                all_discarded = False
                                break
                        if all_discarded and blocked_by:
                            is_disabled = True
                            parent_type = "NG"
                            parent_word = ", ".join(list(blocked_by)[:2])

                # 過去ルール温存＆UI非表示マージ仕様に基づき、
                # すでに他のルールで判定が「確定」しており、非表示フラグがオンの場合は隠す
                if hide_redundant and is_disabled:
                    continue
                    
                visible_items.append((word, count, is_ng, is_ok, is_disabled, parent_word, parent_type, ex_list))

            # グリッド描画
            for idx, (word, count, is_ng, is_ok, is_disabled, parent_word, parent_type, ex_list) in enumerate(visible_items):
                if is_ng:
                    label = f"⛔ ~~{word}~~"
                    val = True if mode_key == "NG" else False
                elif is_ok:
                    label = f"✅ **{word}**"
                    val = True if mode_key == "OK" else False
                elif is_disabled:
                    if parent_type == "NG":
                        label = f"⛔({parent_word}) ~~{word}~~"
                    else:
                        label = f"✅({parent_word}) **{word}**"
                    val = False
                else:
                    label = f"{word}"
                    val = False

                tooltip = f"【{word}】の例:\n" + "\n".join([f"・{t}" for t in ex_list]) if ex_list else "サンプルなし"
                unique_key = f"chk_ngram_{conf['n']}_{word}_v{view_ver}"
                
                col = cols[idx % 4]
                col.checkbox(
                    f"{label} ({count}) {make_google_link(word)}",
                    value=val,
                    key=unique_key,
                    disabled=is_disabled,
                    help=tooltip,
                    on_change=toggle_ngram_word,
                    args=(word, mode_key, unique_key)
                )

# ==========================================
# Step 4: LLM自動判定
# ==========================================
elif choice == "Step 4: LLM自動判定":
    st.title("LLM自動判定")
    st.markdown("N-gramで仕分けきれなかった「グレーゾーン」のデータに対し、OpenAI互換API（LM Studio等）を実行して自動仕分けを行います。")
    
    # 前提データチェック
    if not os.path.exists(PATH_TARGET_FOR_LLM):
        st.warning("前提データ (target_for_llm.jsonl) が存在しません。まず Step 3 を完了してください。")
        st.stop()

    total_gray_count = count_lines(PATH_TARGET_FOR_LLM)
    st.info(f"現在の判定対象（グレーゾーン）: {total_gray_count} 件")

    # APIパラメータ設定
    st.subheader("LLM接続設定")
    c1, c2 = st.columns(2)
    with c1:
        base_url = st.text_input("API Base URL", value="http://localhost:1234/v1")
        model_name = st.text_input("モデル名 (Model)", value="local-model")
    with c2:
        api_key = st.text_input("API Key", value="lm-studio")
        test_limit = st.number_input("テスト制限件数 (0で全件処理)", min_value=0, max_value=5000, value=10)

    use_web_search = st.checkbox("Web検索 (DuckDuckGo) を実行して補足情報を取得する (※1件につき約1秒スリープします)", value=True)

    st.divider()

    # 進捗ファイルのパス
    PATH_LLM_PROGRESS = f"{DATA_DIR}/llm_progress.json"

    def load_progress(path):
        # 1. インメモリのグローバル進捗を優先取得 (マルチスレッド同一プロセスでの最速・確実な同期)
        try:
            from modules.llm_pipeline import get_progress
            prog = get_progress()
            # 処理が走っている (runningがTrue)、または完了している (completedがTrue) 場合にメモリデータを採用
            if prog and (prog.get("running") or prog.get("completed")):
                return prog
        except Exception:
            pass

        # 2. メモリ上から取得できなかった場合は物理ファイルを読み込む (フォールバック)
        if not os.path.exists(path):
            return None
        # Windows環境等でのファイルロック・競合回避のためのリトライ機構
        for _ in range(5):
            try:
                with open(path, 'r', encoding='utf-8', errors='replace') as f:
                    return json.load(f)
            except (IOError, PermissionError, json.JSONDecodeError):
                time.sleep(0.05)  # 50ms待機してリトライ
        return None

    progress_data = load_progress(PATH_LLM_PROGRESS)
    is_running = bool(progress_data.get("running", False)) if progress_data else False

    # 二重実行防止のためにボタンを活性/非活性化
    if st.button("LLM判定を開始する", type="primary", disabled=is_running, use_container_width=True):
        if os.path.exists(PATH_LLM_PROGRESS):
            try:
                os.remove(PATH_LLM_PROGRESS)
            except:
                pass
        
        # 開始前にインメモリの進捗データを即座にリセット（UI状態の同期ズレ防止）
        try:
            from modules.llm_pipeline import set_progress
            set_progress({
                "running": True,
                "current": 0,
                "total": test_limit if (test_limit and test_limit > 0) else 1,
                "title": "準備中...",
                "completed": False,
                "error": None,
                "stop_requested": False,
                "web_status": "待機中..."
            })
        except Exception as e:
            print(f"[Streamlit] メモリ進捗初期化エラー: {e}", flush=True)
        
        import threading
        from modules.llm_pipeline import run_llm_judgment_background
        
        # コンソールへ起動ログを出力（デバッグ用）
        print("="*60, flush=True)
        print("[Streamlit] LLM判定スレッドを起動します...", flush=True)
        print(f"  Input: {PATH_TARGET_FOR_LLM}", flush=True)
        print(f"  Output: {PATH_LLM_JUDGMENTS}", flush=True)
        print(f"  Model: {model_name} (Base URL: {base_url})", flush=True)
        print("="*60, flush=True)
        
        # 非同期スレッドで判定実行
        t = threading.Thread(
            target=run_llm_judgment_background,
            kwargs={
                "input_jsonl": PATH_TARGET_FOR_LLM,
                "output_jsonl": PATH_LLM_JUDGMENTS,
                "base_url": base_url,
                "api_key": api_key,
                "model_name": model_name,
                "use_web_search": use_web_search,
                "test_limit": test_limit if test_limit > 0 else None,
                "progress_path": PATH_LLM_PROGRESS,
                "original_jsonl": PATH_SUFFIX_FILTERED,
                "output_merged_jsonl": PATH_MERGED_FOR_VERIFICATION
            }
        )
        t.daemon = True
        t.start()
        
        st.success("バックグラウンドでLLM判定プロセスを起動しました。")
        time.sleep(0.5)
        st.rerun()

    # 過去データクリアボタン (実行中でない場合のみ有効化)
    if st.button("過去の判定データを初期化", disabled=is_running, use_container_width=True):
        files_to_remove = [PATH_LLM_JUDGMENTS, PATH_MERGED_FOR_VERIFICATION, PATH_LLM_PROGRESS]
        removed_files = []
        for f_path in files_to_remove:
            if os.path.exists(f_path):
                try:
                    os.remove(f_path)
                    removed_files.append(os.path.basename(f_path))
                except Exception as e:
                    st.error(f"ファイル削除エラー ({f_path}): {e}")
        
        # セッション上の判定状況もリセット
        if "verifications" in st.session_state:
            st.session_state["verifications"] = {}
            
        if removed_files:
            st.success(f"以下のファイルをクリアしました: {', '.join(removed_files)}")
        else:
            st.info("初期化する過去データは存在しませんでした。")
        time.sleep(1.5)
        st.rerun()

    # 進捗状況の表示
    if progress_data:
        st.subheader("判定プロセスのステータス")
        
        curr = progress_data.get("current", 0)
        tot = progress_data.get("total", 1)
        title = progress_data.get("title", "")
        completed = progress_data.get("completed", False)
        error = progress_data.get("error", None)

        # リアルタイムで書き出されている判定結果を読み込んで集計
        judged_records = []
        if os.path.exists(PATH_LLM_JUDGMENTS):
            try:
                with open(PATH_LLM_JUDGMENTS, 'r', encoding='utf-8', errors='replace') as f:
                    for line in f:
                        if line.strip():
                            judged_records.append(json.loads(line))
            except:
                pass

        yes_count = sum(1 for r in judged_records if r.get("judgment") is True)
        no_count = sum(1 for r in judged_records if r.get("judgment") is False)
        unknown_count = sum(1 for r in judged_records if r.get("judgment") is None)
        
        if error:
            st.error(f"エラーが発生しました: {error}")
            if st.button("進捗ログをクリアしてやり直す"):
                if os.path.exists(PATH_LLM_PROGRESS):
                    try:
                        os.remove(PATH_LLM_PROGRESS)
                    except:
                        pass
                st.rerun()
        elif completed:
            st.success(f"LLM自動判定およびデータのマージが完了しました。\n\nステータス: {title}")
            
            # 完了サマリー表示
            st.markdown("##### 最終判定サマリー")
            c1, c2, c3 = st.columns(3)
            c1.metric("楽譜判定 (YES)", f"{yes_count} 件")
            c2.metric("ノイズ判定 (NO)", f"{no_count} 件")
            c3.metric("判定不能 (UNKNOWN)", f"{unknown_count} 件")
            
            st.info("「Step 5: 最終査読と確定」へ進み、判定結果を確認してください。")
            if st.button("進捗ログをクリア"):
                if os.path.exists(PATH_LLM_PROGRESS):
                    try:
                        os.remove(PATH_LLM_PROGRESS)
                    except:
                        pass
                st.rerun()
        else:
            # 進捗バーと詳細表示
            progress_val = min(1.0, max(0.0, curr / tot))
            st.progress(progress_val)
            
            web_status = progress_data.get("web_status", "待機中")
            st.info(
                f"進捗: {curr} / {tot} 件 (残り {tot - curr} 件)\n\n"
                f"**現在処理中:** {title}\n\n"
                f"**📡 Web検索状況:** {web_status}"
            )
            
            # 中断処理ボタン
            if st.button("処理を中断する", use_container_width=True):
                if progress_data:
                    progress_data["stop_requested"] = True
                    try:
                        # メモリ上の状態にも即時中断シグナルを適用
                        from modules.llm_pipeline import set_progress
                        set_progress({"stop_requested": True})
                        
                        with open(PATH_LLM_PROGRESS, 'w', encoding='utf-8') as f:
                            json.dump(progress_data, f, ensure_ascii=False, indent=2)
                        st.warning("中断を要求しました。現在の1件が完了次第、安全に停止してマージを行います。")
                        time.sleep(1.5)
                        st.rerun()
                    except Exception as e:
                        st.error(f"中断処理の書き込みに失敗しました: {e}")
            
            # リアルタイムの集計を表示
            st.markdown("##### 判定内訳 (途中経過)")
            c1, c2, c3 = st.columns(3)
            c1.metric("楽譜判定 (YES)", f"{yes_count} 件")
            c2.metric("ノイズ判定 (NO)", f"{no_count} 件")
            c3.metric("判定不能 (UNKNOWN)", f"{unknown_count} 件")
            
            # 直近5件のリアルタイムログ
            if judged_records:
                with st.expander("直近の判定ログを表示", expanded=True):
                    recent = judged_records[-5:] # 最新の5件
                    for r in reversed(recent):
                        j_val = r.get("judgment")
                        if j_val is True:
                            badge = '<span class="custom-badge custom-badge-yes">楽譜</span>'
                        elif j_val is False:
                            badge = '<span class="custom-badge custom-badge-no">ノイズ</span>'
                        else:
                            badge = '<span class="custom-badge custom-badge-unknown">不明</span>'
                        
                        st.markdown(f"**{r.get('label')}** : {badge}", unsafe_allow_html=True)
                        st.caption(f"reason: {r.get('reason')}")
                
                # スクロール可能な判定履歴一覧テーブルの表示を追加
                with st.expander("判定履歴一覧を表示", expanded=False):
                    df_log = pd.DataFrame([
                        {
                            "No.": i + 1,
                            "資料名": r.get("label"),
                            "判定": "楽譜" if r.get("judgment") is True else ("ノイズ" if r.get("judgment") is False else "不明"),
                            "判定理由": r.get("reason")
                        }
                        for i, r in enumerate(judged_records)
                    ])
                    st.dataframe(
                        df_log,
                        use_container_width=True,
                        hide_index=True,
                        column_config={
                            "No.": st.column_config.NumberColumn(width=60),
                            "資料名": st.column_config.TextColumn(width=200),
                            "判定": st.column_config.TextColumn(width=120),
                            "判定理由": st.column_config.TextColumn(width=420)
                        }
                    )
            
            # 自動更新
            time.sleep(2)
            st.rerun()

# ==========================================
# Step 4-B: 音楽メタデータ付与
# ==========================================
elif choice == "Step 4-B: 音楽メタデータ付与":
    st.title("音楽的メタデータの自動推定 (LLM)")
    st.markdown("楽譜として判定された資料に対して、LLM（OpenAI互換API）を使用して「大ジャンル」「サブジャンル」「使用楽器」を自動推定します。")

    # 前提データチェック
    if not os.path.exists(PATH_MERGED_FOR_VERIFICATION):
        st.warning("前提データ (merged_for_verification.jsonl) が存在しません。まず Step 4 のLLM自動判定を完了してください。")
        st.stop()

    # 楽譜と判定されている件数をカウント
    target_count = 0
    with open(PATH_MERGED_FOR_VERIFICATION, 'r', encoding='utf-8', errors='replace') as f:
        for line in f:
            if line.strip():
                try:
                    data = json.loads(line)
                    if data.get("_inferred_metadata", {}).get("is_score") is True:
                        target_count += 1
                except:
                    continue

    st.info(f"推定対象レコード (判定結果が楽譜の資料): {target_count} 件")

    # APIパラメータ設定
    st.subheader("LLM接続設定")
    c1, c2 = st.columns(2)
    with c1:
        base_url = st.text_input("API Base URL (メタデータ付与用)", value="http://localhost:1234/v1", key="enrich_base_url")
        model_name = st.text_input("モデル名 (Model) (メタデータ付与用)", value="local-model", key="enrich_model_name")
    with c2:
        api_key = st.text_input("API Key (メタデータ付与用)", value="lm-studio", type="password", key="enrich_api_key")
        test_limit = st.number_input("テスト制限件数 (0で全件処理) (メタデータ付与用)", min_value=0, max_value=5000, value=10, key="enrich_test_limit")

    st.divider()

    # 進捗ロード
    from modules.metadata_enricher import get_progress, set_progress
    progress_data = get_progress()
    
    # 物理ファイルが存在すればロード（メモリと物理の同期）
    if os.path.exists(PATH_METADATA_PROGRESS):
        try:
            with open(PATH_METADATA_PROGRESS, 'r', encoding='utf-8') as f:
                f_prog = json.load(f)
                if f_prog.get("running") or f_prog.get("completed"):
                    progress_data = f_prog
        except:
            pass

    is_running = progress_data.get("running", False)

    # 推定開始ボタン
    if st.button("音楽メタデータの推定を開始する", type="primary", disabled=is_running, use_container_width=True):
        if os.path.exists(PATH_METADATA_PROGRESS):
            try: os.remove(PATH_METADATA_PROGRESS)
            except: pass
        if os.path.exists(PATH_ENRICHED_METADATA):
            try: os.remove(PATH_ENRICHED_METADATA)
            except: pass

        set_progress({
            "running": True,
            "current": 0,
            "total": test_limit if test_limit > 0 else (target_count if target_count > 0 else 1),
            "title": "準備中...",
            "completed": False,
            "error": None,
            "stop_requested": False
        })

        import threading
        t = threading.Thread(
            target=run_metadata_enrichment_background,
            kwargs={
                "input_jsonl": PATH_MERGED_FOR_VERIFICATION,
                "output_jsonl": PATH_ENRICHED_METADATA,
                "base_url": base_url,
                "api_key": api_key,
                "model_name": model_name,
                "test_limit": test_limit if test_limit > 0 else None,
                "progress_path": PATH_METADATA_PROGRESS
            }
        )
        t.daemon = True
        t.start()

        st.success("バックグラウンドで音楽メタデータ推定プロセスを起動しました。")
        time.sleep(0.5)
        st.rerun()

    # 過去データ初期化
    if st.button("メタデータ付与データをクリア", disabled=is_running, use_container_width=True):
        files_to_remove = [PATH_ENRICHED_METADATA, PATH_METADATA_PROGRESS]
        removed = []
        for f_path in files_to_remove:
            if os.path.exists(f_path):
                try:
                    os.remove(f_path)
                    removed.append(os.path.basename(f_path))
                except Exception as e:
                    st.error(f"削除エラー: {e}")
        if removed: st.success(f"クリア完了: {', '.join(removed)}")
        time.sleep(1)
        st.rerun()

    # 進捗表示
    if progress_data and (progress_data.get("running") or progress_data.get("completed") or progress_data.get("error")):
        st.subheader("推定プロセスのステータス")
        
        curr = progress_data.get("current", 0)
        tot = progress_data.get("total", 1)
        title = progress_data.get("title", "")
        completed = progress_data.get("completed", False)
        error = progress_data.get("error", None)

        if error:
            st.error(f"エラー発生: {error}")
        elif completed:
            st.success("音楽メタデータの推定が完了しました！")
            
            # マージ処理
            if st.button("推定したメタデータを査読用データにマージする", type="primary", use_container_width=True):
                with st.spinner("マージを実行中..."):
                    m_cnt = merge_enriched_metadata(
                        original_merged_jsonl=PATH_MERGED_FOR_VERIFICATION,
                        enriched_jsonl=PATH_ENRICHED_METADATA,
                        output_merged_jsonl=PATH_MERGED_FOR_VERIFICATION
                    )
                    st.success(f"マージ完了！ {m_cnt} 件のレコードにメタデータを反映しました。")
                    time.sleep(2)
                    st.rerun()
        else:
            progress_val = min(1.0, max(0.0, curr / tot))
            st.progress(progress_val)
            st.info(f"進捗: {curr} / {tot} 件 (残り {tot - curr} 件)\n\n**現在処理中:** {title}")
            
            if st.button("処理を中断する", key="stop_enrich", use_container_width=True):
                progress_data["stop_requested"] = True
                set_progress({"stop_requested": True})
                try:
                    with open(PATH_METADATA_PROGRESS, 'w', encoding='utf-8') as f:
                        json.dump(progress_data, f, ensure_ascii=False, indent=2)
                    st.warning("中断要求を送信しました。現在の処理が完了次第停止します。")
                    time.sleep(1)
                    st.rerun()
                except Exception as e:
                    st.error(f"エラー: {e}")

        # 推定されたデータの集計と一覧表示
        enriched_records = []
        if os.path.exists(PATH_ENRICHED_METADATA):
            try:
                with open(PATH_ENRICHED_METADATA, 'r', encoding='utf-8') as f:
                    for line in f:
                        if line.strip():
                            enriched_records.append(json.loads(line))
            except:
                pass

        if enriched_records:
            st.markdown("##### 推定済みデータ内訳")
            genres_list = [r.get("genre", "不明") for r in enriched_records]
            instruments_list = []
            for r in enriched_records:
                instruments_list.extend(r.get("instruments", []))
            
            c_g, c_i = st.columns(2)
            with c_g:
                st.markdown("**ジャンル別集計:**")
                g_counts = Counter(genres_list)
                st.write(pd.DataFrame([{"ジャンル": k, "件数": v} for k, v in g_counts.items()]))
            with c_i:
                st.markdown("**楽器別集計:**")
                i_counts = Counter(instruments_list)
                st.write(pd.DataFrame([{"楽器": k, "件数": v} for k, v in i_counts.items()]))

            with st.expander("直近の推定履歴を表示", expanded=True):
                for r in reversed(enriched_records[-5:]):
                    st.markdown(f"**{r.get('label')}** : `{r.get('genre')}` (`{r.get('subgenre') or 'サブジャンルなし'}`) - 楽器: `{', '.join(r.get('instruments', []))}`")
                    st.caption(f"根拠: {r.get('reason')}")

            # 自動更新
            if is_running:
                time.sleep(2)
                st.rerun()

# ==========================================
# Step 5: 最終査読と確定
# ==========================================
elif choice == "Step 5: 最終査読と確定":
    # ページ遷移ショートカットJSを注入
    inject_pagination_shortcut()
    
    st.title("最終査読と成果物出力")
    st.markdown("LLMによるグレー判定結果を人間が確認・修正し、最終的な合格楽譜レコードを確定させます。")
    
    # 前提データチェック
    if not os.path.exists(PATH_MERGED_FOR_VERIFICATION):
        st.warning("前提データ (merged_for_verification.jsonl) が存在しません。まず Step 4 のLLM判定を完了してください。")
        st.stop()

    # データのロード (キャッシュを無効化し、エラー耐性を高めて最新のファイルを即時ロード)
    def load_merged_data(path):
        rows = []
        if not os.path.exists(path):
            return rows
        with open(path, 'r', encoding='utf-8', errors='replace') as f:
            for line in f:
                try:
                    rows.append(json.loads(line))
                except Exception:
                    continue
        return rows

    data_list = load_merged_data(PATH_MERGED_FOR_VERIFICATION)
    
    if "verifications" not in st.session_state:
        st.session_state["verifications"] = {} # id -> bool
        
    if "enriched_metadata" not in st.session_state:
        st.session_state["enriched_metadata"] = {} # id -> dict

    # LLM判定結果による絞り込み機能とキーワード検索機能の追加
    c_filt1, c_filt2 = st.columns([1, 1])
    with c_filt1:
        filter_option = st.selectbox(
            "LLM判定による絞り込み",
            ["すべて表示", "LLMが「楽譜 (YES)」と判定したレコードのみ", "LLMが「ノイズ (NO)」と判定したレコードのみ", "LLMが「不明 (UNKNOWN)」と判定したレコードのみ"],
            index=0
        )
    with c_filt2:
        search_keyword = st.text_input("🔍 タイトル検索（部分一致）", value="")
    
    # フィルタの適用
    filtered_list = []
    for item in data_list:
        inf_meta = item.get("_inferred_metadata", {})
        llm_decision = inf_meta.get("is_score")
        
        if filter_option == "LLMが「楽譜 (YES)」と判定したレコードのみ" and llm_decision is not True:
            continue
        elif filter_option == "LLMが「ノイズ (NO)」と判定したレコードのみ" and llm_decision is not False:
            continue
        elif filter_option == "LLMが「不明 (UNKNOWN)」と判定したレコードのみ" and llm_decision is not None:
            continue
            
        # タイトル検索フィルタ
        label = item.get("rdfs:label", item.get("schema:name", "No Title"))
        if isinstance(label, list):
            label_str = " ".join([str(x) for x in label])
        else:
            label_str = str(label)
            
        if search_keyword and search_keyword.strip().lower() not in label_str.lower():
            continue
            
        filtered_list.append(item)

    total_items = len(filtered_list)
    
    # 検索または絞り込みが行われている場合のみ、一括操作UIを表示する
    if search_keyword or filter_option != "すべて表示":
        st.markdown(f"**💡 {total_items}件の検索・絞り込み結果に対する一括操作**")
        c_bulk_ok, c_bulk_ng, c_bulk_clear = st.columns(3)
        with c_bulk_ok:
            if st.button("🟢 すべてを「楽譜 (OK)」に変更", key="bulk_ok_btn", use_container_width=True):
                for item in filtered_list:
                    item_id = item.get("@id", item.get("id"))
                    st.session_state["verifications"][item_id] = True
                st.success(f"{total_items} 件を「楽譜 (OK)」に一括変更しました。")
                time.sleep(1)
                st.rerun()
        with c_bulk_ng:
            if st.button("🔴 すべてを「ノイズ (NG)」に変更", key="bulk_ng_btn", use_container_width=True):
                for item in filtered_list:
                    item_id = item.get("@id", item.get("id"))
                    st.session_state["verifications"][item_id] = False
                st.success(f"{total_items} 件を「ノイズ (NG)」に一括変更しました。")
                time.sleep(1)
                st.rerun()
        with c_bulk_clear:
            if st.button("⚪ すべてを「保留」に変更", key="bulk_clear_btn", use_container_width=True):
                for item in filtered_list:
                    item_id = item.get("@id", item.get("id"))
                    st.session_state["verifications"][item_id] = None
                st.success(f"{total_items} 件を「保留」に一括変更しました。")
                time.sleep(1)
                st.rerun()

    st.info(f"要査読レコード: {total_items} 件")

    # グリッド・テーブル形式で査読
    # 表示件数の動的選択を追加
    page_size = st.selectbox("1ページあたりの表示件数", [10, 20, 50, 100], index=1)
    
    # ページ状態のセッション初期化
    if "verification_page" not in st.session_state:
        st.session_state["verification_page"] = 1

    total_pages = (total_items - 1) // page_size + 1 if total_items > 0 else 1
    
    # 範囲外チェックと補正
    if st.session_state["verification_page"] > total_pages:
        st.session_state["verification_page"] = total_pages
    if st.session_state["verification_page"] < 1:
        st.session_state["verification_page"] = 1

    # ナビゲーションボタンと入力フィールドの配置
    page = render_pagination(total_pages, st.session_state["verification_page"], "top")
    
    start_idx = (page - 1) * page_size
    end_idx = min(start_idx + page_size, total_items)
    
    page_items = filtered_list[start_idx:end_idx]

    st.subheader(f"査読対象 ( {start_idx + 1} 〜 {end_idx} 件目 / 全 {total_items} 件 )")
    
    for idx, item in enumerate(page_items):
        item_id = item.get("@id", item.get("id"))
        inf_meta = item.get("_inferred_metadata", {})
        llm_decision = inf_meta.get("is_score")
        reason = inf_meta.get("_evidence", {}).get("score_reason", "")
        
        label = item.get("rdfs:label", item.get("schema:name", "No Title"))
        desc = item.get("schema:description", item.get("description", ""))
        
        # セッションに既存の決定がなければLLMの判断で初期化
        if item_id not in st.session_state["verifications"]:
            st.session_state["verifications"][item_id] = llm_decision
            
        if item_id not in st.session_state["enriched_metadata"]:
            st.session_state["enriched_metadata"][item_id] = {
                "genre": inf_meta.get("genre", "その他/不明"),
                "subgenre": inf_meta.get("subgenre"),
                "instruments": inf_meta.get("instruments", [])
            }

        # 説明文の箇条書き整形
        def format_description(d_val):
            if not d_val:
                return "説明情報なし"
            import ast
            if isinstance(d_val, str) and d_val.startswith('[') and d_val.endswith(']'):
                try:
                    d_val = ast.literal_eval(d_val)
                except:
                    pass
            if isinstance(d_val, list):
                items = []
                for x in d_val:
                    if isinstance(x, str) and x.startswith('[') and x.endswith(']'):
                        try:
                            items.extend(ast.literal_eval(x))
                        except:
                            items.append(x)
                    else:
                        items.append(x)
                return "\n".join([f"- {str(item).strip()}" for item in items if item])
            return str(d_val)

        formatted_desc = format_description(desc)

        # その他のメタデータ整理（日本語ラベルへマッピング）
        other_metadata = {}
        for k, v in item.items():
            if k in ['_inferred_metadata', 'is_score']: 
                continue
            friendly_key = k
            if k == '@id' or k == 'id': friendly_key = "ID / URL"
            elif k == 'rdfs:label': friendly_key = "ラベル"
            elif k == 'schema:name': friendly_key = "名称"
            elif k == 'schema:description' or k == 'description': friendly_key = "説明"
            elif k == 'schema:about': friendly_key = "関連テーマ (about)"
            elif k == 'schema:creator' or k == 'creator': friendly_key = "作成者/著者"
            elif k == 'schema:publisher' or k == 'publisher': friendly_key = "所蔵先"
            
            if isinstance(v, list):
                other_metadata[friendly_key] = ", ".join([str(x) for x in v if x])
            else:
                other_metadata[friendly_key] = str(v)

        jpsearch_link = get_japan_search_link(item)
        c1, c2, c3 = st.columns([5, 3, 2])
        with c1:
            image_url = item.get("schema:image")
            if isinstance(image_url, list) and image_url:
                image_url = image_url[0]
            
            if image_url and isinstance(image_url, str):
                col_img, col_txt = st.columns([1, 4])
                with col_img:
                    st.image(image_url, use_container_width=True)
                with col_txt:
                    if jpsearch_link:
                        st.markdown(f"**[{start_idx + idx + 1}] [{label}]({jpsearch_link})**")
                    else:
                        st.markdown(f"**[{start_idx + idx + 1}] {label}**")
                    st.markdown(formatted_desc)
            else:
                if jpsearch_link:
                    st.markdown(f"**[{start_idx + idx + 1}] [{label}]({jpsearch_link})**")
                else:
                    st.markdown(f"**[{start_idx + idx + 1}] {label}**")
                st.markdown(formatted_desc)
            
            # オリジナルメタデータの詳細アコーディオン
            with st.expander("オリジナルメタデータの詳細を表示"):
                for k_f, v_f in other_metadata.items():
                    if k_f == "ID / URL" and str(v_f).startswith("http"):
                        st.markdown(f"**{k_f}**: [{v_f}]({v_f})")
                    else:
                        st.markdown(f"**{k_f}**: {v_f}")

            # Web検索スニペットの表示
            web_snippets = inf_meta.get("_evidence", {}).get("retrieved_web_snippets", [])
            if web_snippets:
                web_text = web_snippets[0] if isinstance(web_snippets, list) and len(web_snippets) > 0 else str(web_snippets)
                if web_text and web_text != "None" and web_text != "検索結果なし":
                    with st.expander("Web検索の補足情報を表示"):
                        st.info(web_text)
                        
        with c2:
            if llm_decision is True:
                badge_html = '<span class="custom-badge custom-badge-yes">楽譜</span>'
            elif llm_decision is False:
                badge_html = '<span class="custom-badge custom-badge-no">ノイズ</span>'
            else:
                badge_html = '<span class="custom-badge custom-badge-unknown">不明</span>'
            
            st.markdown(f"**LLM判断:** {badge_html}", unsafe_allow_html=True)
            st.caption(f"理由: {reason}")
        with c3:
            v_val = st.session_state["verifications"][item_id]
            user_val = st.radio(
                "判定:", 
                ("楽譜 (OK)", "ノイズ (NG)", "保留 / 判定待ち"), 
                index=0 if v_val is True else (1 if v_val is False else 2),
                key=f"rad_verify_{item_id}_{v_val}"
            )
            if "楽譜" in user_val:
                st.session_state["verifications"][item_id] = True
            elif "ノイズ" in user_val:
                st.session_state["verifications"][item_id] = False
            else:
                st.session_state["verifications"][item_id] = None
                
            # 楽譜判定されたもののみ、音楽的メタデータ編集UIを表示
            if st.session_state["verifications"][item_id] is True:
                st.markdown("---")
                st.markdown("**音楽的メタデータ:**")
                enrich_info = st.session_state["enriched_metadata"][item_id]
                
                g_options = list(GENRES.keys())
                g_val = enrich_info.get("genre", "その他/不明")
                default_g_idx = g_options.index(g_val) if g_val in g_options else g_options.index("その他/不明")
                
                sel_genre = st.selectbox(
                    "大ジャンル:",
                    g_options,
                    index=default_g_idx,
                    key=f"sel_genre_{item_id}"
                )
                st.session_state["enriched_metadata"][item_id]["genre"] = sel_genre
                
                sub_genres = GENRES.get(sel_genre, [])
                if sub_genres:
                    sub_options = [None] + sub_genres
                    sub_val = enrich_info.get("subgenre")
                    default_sub_idx = sub_options.index(sub_val) if sub_val in sub_options else 0
                    
                    sel_sub = st.selectbox(
                        "サブジャンル:",
                        sub_options,
                        index=default_sub_idx,
                        format_func=lambda x: "選択なし" if x is None else x,
                        key=f"sel_sub_{item_id}"
                    )
                    st.session_state["enriched_metadata"][item_id]["subgenre"] = sel_sub
                else:
                    st.session_state["enriched_metadata"][item_id]["subgenre"] = None
                    
                cur_insts = enrich_info.get("instruments", [])
                sel_insts = st.multiselect(
                    "使用楽器:",
                    INSTRUMENTS,
                    default=[i for i in cur_insts if i in INSTRUMENTS],
                    key=f"sel_insts_{item_id}"
                )
                st.session_state["enriched_metadata"][item_id]["instruments"] = sel_insts
            
        st.divider()

    # 下部ナビゲーションボタンの配置
    if total_pages > 1:
        render_pagination(total_pages, st.session_state["verification_page"], "bottom")
        st.divider()

    st.subheader("最終成果物の確定出力")
    st.markdown("すべての査読が終わったら（または現状の判断で）、最終クレンジング済みデータを書き出します。")
    
    c_ok = sum(1 for v in st.session_state["verifications"].values() if v is True)
    st.caption(f"現在 確定OK予定件数: {c_ok} 件")

    if st.button("最終成果物を出力する", type="primary", use_container_width=True):
        # 1. 確定OKのN-gramデータを読み込む
        final_records = []
        if os.path.exists(PATH_CONFIRMED_OK):
            with open(PATH_CONFIRMED_OK, 'r', encoding='utf-8') as f:
                for line in f:
                    final_records.append(json.loads(line))
                    
        # 2. 査読したグレーゾーンからOK判定のもののみマージ
        for item in data_list:
            item_id = item.get("@id", item.get("id"))
            if st.session_state["verifications"].get(item_id) is True:
                # ユーザーが修正したメタデータ構造を書き出し
                item["is_score"] = True
                final_records.append(item)
                
        # 3. 音楽的メタデータ（ジャンル、サブジャンル、楽器）の反映
        for item in final_records:
            item_id = item.get("@id", item.get("id"))
            enrich_info = st.session_state["enriched_metadata"].get(item_id)
            if not enrich_info:
                inf = item.get("_inferred_metadata", {})
                enrich_info = {
                    "genre": inf.get("genre", "その他/不明"),
                    "subgenre": inf.get("subgenre"),
                    "instruments": inf.get("instruments", [])
                }
            item["genre"] = enrich_info.get("genre", "その他/不明")
            item["subgenre"] = enrich_info.get("subgenre")
            item["instruments"] = enrich_info.get("instruments", [])
                
        # 4. ファイル書き出し
        os.makedirs(os.path.dirname(PATH_CLEANED_JSONL), exist_ok=True)
        with open(PATH_CLEANED_JSONL, 'w', encoding='utf-8') as f:
            for item in final_records:
                f.write(json.dumps(item, ensure_ascii=False) + '\n')
                
        # 5. 分析用にCSVも書き出し
        df_out = pd.DataFrame(final_records)
        cols_out = ['@id', 'rdfs:label', 'schema:name', 'genre', 'subgenre', 'instruments', 'schema:description']
        valid_cols = [c for c in cols_out if c in df_out.columns]
        other_cols = [c for c in df_out.columns if c not in valid_cols]
        df_out[valid_cols + other_cols].to_csv(PATH_CLEANED_CSV, index=False, encoding='utf-8-sig')
        
        st.success(
            f"最終クレンジングが完了しました。\n"
            f"・成果物 (JSONL): {PATH_CLEANED_JSONL} ({len(final_records)} 件)\n"
            f"・成果物 (CSV): {PATH_CLEANED_CSV}"
        )

# ==========================================
# Step 6: 検索ツールのエクスポート
# ==========================================
elif choice == "Step 6: 検索ツールのエクスポート":
    st.title("資料検索ツールのエクスポート")
    st.markdown("確定したクレンジング済み楽譜データと、音楽的メタデータを使用して、GitHub Pagesに公開可能な「静的検索ポータル（HTML/CSS/JS）」を構築します。")

    # 前提データチェック
    if not os.path.exists(PATH_CLEANED_JSONL):
        st.warning("最終成果物 (classical_scores_cleaned.jsonl) が存在しません。まず Step 5 で「最終成果物を出力する」を完了してください。")
        st.stop()

    st.subheader("エクスポート設定")
    export_dir = st.text_input("エクスポート先ディレクトリ", value=PATH_EXPORT_DIR)
    
    st.info(
        f"以下の場所に検索ポータルを出力します:\n"
        f"・HTML/CSS/JSファイル ➡ `{export_dir}/` 内\n"
        f"・軽量検索用データ ➡ `{export_dir}/scores_data.json`"
    )

    if st.button("検索ポータルをビルドしてエクスポートする", type="primary", use_container_width=True):
        with st.spinner("検索用JSONデータを構築中..."):
            # 軽量JSONの構築
            records = []
            with open(PATH_CLEANED_JSONL, 'r', encoding='utf-8') as f:
                for line in f:
                    if not line.strip(): continue
                    try:
                        data = json.loads(line)
                        label = data.get('rdfs:label')
                        name = data.get('schema:name')
                        title = str(label) if label else (str(name) if name else "No Title")
                        if isinstance(name, list) and name:
                            title = name[0]
                        elif isinstance(title, list) and title:
                            title = title[0]
                        
                        image = data.get('schema:image', '')
                        
                        # 外部リンク取得
                        url = ''
                        access = data.get('https://jpsearch.go.jp/term/property#accessInfo', {})
                        if isinstance(access, dict):
                            url = access.get('schema:url', '')
                        elif isinstance(access, list) and access:
                            url = access[0].get('schema:url', '') if isinstance(access[0], dict) else ''
                        
                        if not url:
                            source = data.get('https://jpsearch.go.jp/term/property#sourceInfo', {})
                            if isinstance(source, dict):
                                url = source.get('schema:url', '')
                        
                        if not url:
                            url = data.get('@id', '')
                        
                        # 説明文の整形
                        desc_val = data.get('schema:description', '') or data.get('description', '')
                        if isinstance(desc_val, list):
                            desc = " ".join([str(x) for x in desc_val])
                        else:
                            desc = str(desc_val)
                        
                        # 日本語以外のゴミ除去やHTMLタグ除去など簡易クリーニング
                        desc = re.sub(r'<[^>]*>', '', desc)
                        if len(desc) > 300:
                            desc = desc[:300] + "..."
                        
                        provider = ''
                        source = data.get('https://jpsearch.go.jp/term/property#sourceInfo', {})
                        if isinstance(source, dict):
                            prov_val = source.get('schema:provider', '')
                            if prov_val:
                                provider = str(prov_val).split('/')[-1]
                        
                        # ルールベースでの初期分類フォールバック（LLM未推定の場合のコールドスタート対策）
                        genre = data.get("genre", "その他/不明")
                        subgenre = data.get("subgenre")
                        instruments = data.get("instruments", [])
                        
                        title_desc_text = (title + " " + desc).lower()
                        
                        if genre == "その他/不明" or not genre:
                            # 雅楽
                            if any(k in title_desc_text for k in ["雅楽", "唐楽", "高麗楽", "朗詠", "催馬楽", "笙", "篳篥", "竜笛", "龍笛"]):
                                genre = "雅楽"
                                if "唐楽" in title_desc_text: subgenre = "唐楽"
                                elif "高麗楽" in title_desc_text: subgenre = "高麗楽"
                                elif "催馬楽" in title_desc_text: subgenre = "催馬楽"
                                elif "朗詠" in title_desc_text: subgenre = "朗詠"
                            # 能楽/謡曲
                            elif any(k in title_desc_text for k in ["能楽", "謡曲", "謡本", "観世", "宝生", "金剛", "喜多", "狂言"]):
                                genre = "能楽/謡曲"
                                if "狂言" in title_desc_text: subgenre = "狂言"
                                elif "謡" in title_desc_text: subgenre = "謡曲"
                                else: subgenre = "能"
                            # 三味線音楽
                            elif any(k in title_desc_text for k in ["三味線", "長唄", "義太夫", "常磐津", "清元", "新内", "地歌", "地唄", "端唄", "俗曲", "小唄"]):
                                genre = "三味線音楽"
                                if "地歌" in title_desc_text or "地唄" in title_desc_text: subgenre = "地歌"
                                elif "長唄" in title_desc_text: subgenre = "長唄"
                                elif "義太夫" in title_desc_text: subgenre = "義太夫節"
                                elif "常磐津" in title_desc_text: subgenre = "常磐津節"
                                elif "清元" in title_desc_text: subgenre = "清元節"
                                elif "新内" in title_desc_text: subgenre = "新内節"
                                else: subgenre = "端唄/俗曲"
                            # 琵琶楽
                            elif any(k in title_desc_text for k in ["琵琶", "平曲", "平家琵琶", "薩摩琵琶", "筑前琵琶"]):
                                genre = "琵琶楽"
                                if "平曲" in title_desc_text or "平家" in title_desc_text: subgenre = "平曲（平家琵琶）"
                                elif "薩摩" in title_desc_text: subgenre = "薩摩琵琶"
                                elif "筑前" in title_desc_text: subgenre = "筑前琵琶"
                            # 尺八楽
                            elif any(k in title_desc_text for k in ["尺八", "琴古", "都山"]):
                                genre = "尺八楽"
                                if "本曲" in title_desc_text: subgenre = "本曲"
                                else: subgenre = "外曲（琴古流・都山流等）"
                            # 声明
                            elif any(k in title_desc_text for k in ["声明", "伽陀", "法会", "引声", "魚山"]):
                                genre = "声明/仏教音楽"
                            # 洋楽
                            elif any(k in title_desc_text for k in ["洋楽", "五線譜", "ピアノ", "バイオリン", "唱歌", "西洋"]):
                                genre = "近現代邦楽/洋楽"

                        if not instruments:
                            # 楽器のフォールバック
                            inst_candidates = {
                                "唄/声": ["唄", "歌", "謡", "声", "唱"],
                                "箏/琴": ["箏", "琴", "こと", "十三絃", "十七絃"],
                                "三味線": ["三味線", "三線"],
                                "尺八": ["尺八"],
                                "琵琶": ["琵琶"],
                                "笙": ["笙"],
                                "篳篥": ["篳篥"],
                                "龍笛/高麗笛/神楽笛": ["龍笛", "竜笛", "高麗笛", "神楽笛"],
                                "篠笛/能管": ["篠笛", "能管", "横笛"],
                                "鼓/太鼓": ["鼓", "小鼓", "大鼓", "太鼓"]
                            }
                            for inst, keywords in inst_candidates.items():
                                if any(kw in title_desc_text for kw in keywords):
                                    instruments.append(inst)

                        records.append({
                            "id": data.get('@id', data.get('id', '')),
                            "title": title,
                            "description": desc,
                            "image": image,
                            "url": url,
                            "provider": provider,
                            "genre": genre,
                            "subgenre": subgenre,
                            "instruments": instruments
                        })
                    except Exception as e:
                        continue

            # JSON書き出し
            out_json_path = f"{export_dir}/scores_data.json"
            os.makedirs(os.path.dirname(out_json_path), exist_ok=True)
            with open(out_json_path, 'w', encoding='utf-8') as jf:
                json.dump(records, jf, ensure_ascii=False, indent=2)

        with st.spinner("静的HTML/CSS/JSテンプレートを書き出し中..."):
            # 静的アセットの書き出し (直接ファイルを作成)
            from modules.importer import copy_static_search_assets
            try:
                copy_static_search_assets(export_dir)
                st.success(
                    f"エクスポートが成功しました！\n\n"
                    f"・出力ディレクトリ: `{export_dir}/`\n"
                    f"・資料登録件数: {len(records)} 件\n\n"
                    f"ローカルでテストするには、以下のコマンドを実行してください:\n"
                    f"`python3 -m http.server --directory {export_dir} 8000`"
                )
            except Exception as e:
                st.error(f"静的ファイルの書き出しに失敗しました: {e}")

