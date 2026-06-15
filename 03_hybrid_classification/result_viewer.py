# -*- coding: utf-8 -*-
import streamlit as st
import json
import os

# =================設定=================
st.set_page_config(
    layout="wide",
    page_title="日本古典籍楽譜 査読・修正ツール",
    page_icon="👩‍🏫"
)

# 入力ファイル（マージ済みの詳細データ）
INPUT_FILE = "fragments/merged_for_verification.jsonl"
# 出力ファイル（人間が最終確定させたフルデータ）
OUTPUT_FILE = "fragments/human_verified_scores.jsonl"
# ======================================

# カスタムCSSの適用 (バッジのスタイル定義)
st.markdown("""
<style>
    .reportview-container {
        background: #f8f9fa;
    }
    .badge {
        display: inline-block;
        padding: 4px 8px;
        border-radius: 4px;
        font-size: 0.8rem;
        font-weight: bold;
        color: white;
        margin-right: 5px;
    }
    .badge-primary { background-color: #007bff; }
    .badge-secondary { background-color: #6c757d; }
    .badge-success { background-color: #28a745; }
    .badge-danger { background-color: #dc3545; }
    .badge-warning { background-color: #ffc107; color: #212529; }
</style>
""", unsafe_allow_html=True)

# データのロード
@st.cache_data
def load_raw_data():
    if not os.path.exists(INPUT_FILE):
        return []
    records = []
    with open(INPUT_FILE, 'r', encoding='utf-8') as f:
        for line in f:
            try:
                records.append(json.loads(line))
            except:
                continue
    return records

def get_id(data):
    for key in ['id', '@id', 'uri', 'url']:
        if key in data:
            return data[key]
    return "Unknown_ID"

# データのセッションステート初期化
if "records" not in st.session_state:
    st.session_state["records"] = load_raw_data()
    # 人間の判定を初期値でロード
    st.session_state["human_decisions"] = {}
    for r in st.session_state["records"]:
        rid = get_id(r)
        inf = r.get("_inferred_metadata", {})
        st.session_state["human_decisions"][rid] = inf.get("is_score")

# 変更フラグの初期化
if "changed" not in st.session_state:
    st.session_state["changed"] = False

def update_decision(rid, val):
    st.session_state["human_decisions"][rid] = val
    st.session_state["changed"] = True

def save_verified_data():
    """人間が査読したデータを元のリッチな構造のまま保存する"""
    saved_count = 0
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        for r in st.session_state["records"]:
            rid = get_id(r)
            # 人間が修正した値を取得
            current_val = st.session_state["human_decisions"].get(rid)
            
            # _inferred_metadata を更新
            if "_inferred_metadata" not in r:
                r["_inferred_metadata"] = {}
            r["_inferred_metadata"]["is_score"] = current_val
            r["_inferred_metadata"]["verified_by_human"] = True
            
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
            saved_count += 1
            
    st.session_state["changed"] = False
    return saved_count

# =================メインUI=================
st.title("👩‍🏫 日本古典籍楽譜 査読・修正ツール")
st.markdown("AIによる楽譜の判定結果（Web検索RAGを含む）を目視検証します。元の豊富なメタデータや画像情報も参照できます。")

records = st.session_state["records"]

if not records:
    st.error(f"ファイルが見つかりません: {INPUT_FILE}")
else:
    # --- サイドバー ---
    with st.sidebar:
        st.header("💾 アクション")
        
        # 修正情報のステータス
        st.metric("査読対象の総件数", f"{len(records)} 件")
        
        if st.button("💾 確定データを保存", type="primary"):
            count = save_verified_data()
            st.success(f"保存完了！ ({count} 件)\n出力先: {OUTPUT_FILE}")
            st.toast("データを保存しました！", icon="💾")
            
        st.divider()
        st.header("🔍 フィルター設定")
        
        # 判定ステータスで絞り込み
        filter_status = st.radio(
            "表示する判定ステータス（現在の状態）:",
            ("すべて", "✅ 楽譜（True）", "❌ 除外（False）", "❓ 判定不能（Null/Unknown）")
        )
        
        st.divider()
        search_query = st.text_input("🔍 キーワード検索（タイトルなど）", "")

    # --- データのフィルタリング ---
    filtered_records = []
    for r in records:
        rid = get_id(r)
        current_decision = st.session_state["human_decisions"].get(rid)
        
        # タイトルの取得 (rdfs:label を最優先)
        label = r.get('rdfs:label')
        if label:
            title = str(label)
        else:
            name = r.get('schema:name')
            if isinstance(name, list) and name:
                # リストの場合は要素を探す
                title = str(name[0])
            else:
                title = str(name) if name else "No Title"
            
        # ステータスフィルター
        if filter_status == "✅ 楽譜（True）" and current_decision is not True:
            continue
        elif filter_status == "❌ 除外（False）" and current_decision is not False:
            continue
        elif filter_status == "❓ 判定不能（Null/Unknown）" and current_decision is not None:
            continue
            
        # 検索キーワードフィルター
        if search_query:
            match = False
            if search_query.lower() in title.lower():
                match = True
            desc = r.get("schema:description", [])
            desc_str = " ".join(desc) if isinstance(desc, list) else str(desc)
            if search_query.lower() in desc_str.lower():
                match = True
            if not match:
                continue
                
        filtered_records.append((r, rid, title))

    st.markdown(f"**表示中の件数: {len(filtered_records)} 件**")
    st.divider()

    # --- リスト表示 ---
    for r, rid, title in filtered_records:
        inf = r.get("_inferred_metadata", {})
        evidence = inf.get("_evidence", {})
        
        current_decision = st.session_state["human_decisions"].get(rid)
        
        # 全体を枠線付きのカードコンテナで囲む (表示崩れを完全に防ぐ)
        with st.container(border=True):
            # 3カラムレイアウト [画像(あれば)] - [詳細情報] - [判定修正]
            has_image = "schema:image" in r and r["schema:image"]
            
            if has_image:
                col_img, col_info, col_action = st.columns([1.5, 5.5, 3])
            else:
                col_info, col_action = st.columns([7, 3])
                
            # 1. 画像表示 (ある場合のみ)
            if has_image:
                with col_img:
                    st.image(r["schema:image"], use_container_width=True, caption="書影/サンプル")
                    
            # 2. 詳細情報表示
            with col_info:
                # 判定状態に応じたカラーヘッダー（バッジ）を最上部に表示
                if current_decision is True:
                    status_badge = '<div style="background-color: #e6fffa; color: #00664f; border: 1px solid #b2f5ea; padding: 6px 12px; border-radius: 6px; font-weight: bold; display: inline-block; margin-bottom: 12px;">🟢 確定状態: 楽譜 (YES)</div>'
                elif current_decision is False:
                    status_badge = '<div style="background-color: #fff5f5; color: #9b2c2c; border: 1px solid #fed7d7; padding: 6px 12px; border-radius: 6px; font-weight: bold; display: inline-block; margin-bottom: 12px;">🔴 確定状態: 除外 (NO)</div>'
                else:
                    status_badge = '<div style="background-color: #fffbeb; color: #975a16; border: 1px solid #fef3c7; padding: 6px 12px; border-radius: 6px; font-weight: bold; display: inline-block; margin-bottom: 12px;">🟡 未確定: 判定不能 (UNKNOWN)</div>'
                
                st.markdown(status_badge, unsafe_allow_html=True)

                # タイトルとID
                st.markdown(f"### {title}")
                if rid.startswith("http"):
                    st.caption(f"ID: [{rid}]({rid})")
                else:
                    st.caption(f"ID: {rid}")
                
                # 各種バッジ
                stage = evidence.get("stage", "unknown")
                stage_label = "1次判定 (メタデータ)" if stage == "primary_metadata" else "2次判定 (Web検索)"
                stage_class = "badge-primary" if stage == "primary_metadata" else "badge-secondary"
                
                ai_decision = inf.get("is_score")
                ai_label = "AI: 楽譜" if ai_decision is True else ("AI: 除外" if ai_decision is False else "AI: 不明")
                ai_class = "badge-success" if ai_decision is True else ("badge-danger" if ai_decision is False else "badge-warning")
                
                st.markdown(f'<span class="badge {stage_class}">{stage_label}</span> <span class="badge {ai_class}">{ai_label}</span>', unsafe_allow_html=True)
                
                # オリジナルメタデータ（説明文）
                st.markdown("**【元のメタデータ（説明・分類）】**")
                desc = r.get("schema:description")
                if desc:
                    if isinstance(desc, list):
                        for d in desc:
                            st.markdown(f"- {d}")
                    else:
                        st.markdown(f"- {desc}")
                else:
                    st.caption("説明文なし")
                    
                # 提供元やジャンル
                provider = r.get("https://jpsearch.go.jp/term/property#accessInfo", {}).get("schema:provider", "不明")
                st.markdown(f"**提供元/アーカイブ**: {provider}")
                
                # AIの判定理由
                reason = evidence.get("score_reason", "理由なし")
                st.info(f"🤖 **AIの判定理由**: {reason}")
                
            # 3. 判定修正
            with col_action:
                st.markdown("👈 **人間の判定・修正**")
                
                # 選択肢定義
                options = ["楽譜（YES）", "除外（NO）", "判定不能（UNKNOWN）"]
                
                # 現在値のインデックス設定
                current_idx = 2 # デフォルト: 不明
                if current_decision is True:
                    current_idx = 0
                elif current_decision is False:
                    current_idx = 1
                    
                choice = st.radio(
                    "判定:",
                    options,
                    index=current_idx,
                    key=f"radio_{rid}",
                    horizontal=False,
                    label_visibility="collapsed"
                )
                
                # 値が変更された場合のコールバック
                new_val = None
                if choice == "楽譜（YES）":
                    new_val = True
                elif choice == "除外（NO）":
                    new_val = False
                    
                if new_val != current_decision:
                    update_decision(rid, new_val)
                    st.toast(f"「{title}」の判定を更新しました。必ずサイドバーの保存を押してください。", icon="💡")
                    st.rerun()
        st.divider()