import streamlit as st
import pandas as pd
import json
import os

# =================設定=================
st.set_page_config(layout="wide", page_title="人間による最終確認ツール")

# 入力ファイル（LLMの判定結果）
INPUT_FILE = "fragments/llm_judgments.jsonl" 
# ※ high_accuracy版を使う場合は書き換えてください

# 出力ファイル（人間が確定させた結果）
OUTPUT_FILE = "fragments/human_verified_scores.jsonl"

# =================関数=================
def load_data():
    if not os.path.exists(INPUT_FILE): return None
    data = []
    with open(INPUT_FILE, 'r', encoding='utf-8') as f:
        for line in f:
            try:
                d = json.loads(line)
                data.append(d)
            except: continue
    
    df = pd.DataFrame(data)
    # 列名統一
    if 'judgment' in df.columns: df = df.rename(columns={'judgment': 'is_score'})
    if 'thought' in df.columns: df = df.rename(columns={'thought': 'reason'})
    
    # IDがないと保存できないため、ない場合は行番号などで補完（念のため）
    if 'id' not in df.columns:
        df['id'] = [f"row_{i}" for i in range(len(df))]
        
    return df

def save_verified_data(original_df, session_judgments):
    """
    original_df: 元のデータフレーム
    session_judgments: {id: True/False} の辞書（変更があったもの）
    """
    # 元データをコピー
    final_df = original_df.copy()
    
    # セッションにある変更を適用
    # apply用の関数
    def apply_judgment(row):
        item_id = row['id']
        # セッションに変更記録があればそれを採用、なければ元のまま
        if item_id in session_judgments:
            return session_judgments[item_id]
        return row['is_score']

    final_df['final_is_score'] = final_df.apply(apply_judgment, axis=1)
    
    # 保存用データの作成（必要なカラムだけ残す）
    # is_score を final_is_score で上書き
    save_records = []
    for _, row in final_df.iterrows():
        record = {
            "id": row['id'],
            "label": row['label'],
            "is_score": bool(row['final_is_score']), # numpy.bool対策
            "llm_reason": row.get('reason', ''),
            "verified_by_human": (row['id'] in session_judgments) # 人間が触ったフラグ
        }
        save_records.append(record)

    # 保存
    os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        for r in save_records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    
    return len(save_records)

# =================メインUI=================
st.title("👩‍🏫 LLM判定結果の査読・修正ツール")
st.markdown("AIの判定結果を確認し、間違いがあれば右側のボタンで修正してください。**最後に必ず「保存」を押してください。**")

df = load_data()

# セッション状態の初期化（人間の判定を記録する辞書）
if "human_decisions" not in st.session_state:
    st.session_state["human_decisions"] = {} 
    # { "http://id...": True(楽譜) / False(除外) }

if df is not None and not df.empty:
    
    # --- サイドバー ---
    with st.sidebar:
        st.header("💾 操作パネル")
        
        # 変更数のカウント
        changes = len(st.session_state["human_decisions"])
        st.metric("修正した件数", f"{changes} 件")
        
        if st.button("データセットを保存する", type="primary"):
            count = save_verified_data(df, st.session_state["human_decisions"])
            st.success(f"保存しました！ (全 {count} 件)\n出力先: {OUTPUT_FILE}")
        
        st.divider()
        st.header("絞り込み表示")
        filter_option = st.radio(
            "表示対象 (AIの判定):",
            ("すべて", "✅ AI: 楽譜 (True)", "❌ AI: 非楽譜 (False)", "❓ AI: 不明 (Null)"),
            index=2 # デフォルトで「除外されたもの」を表示（救済のため）
        )
        
        # 検索機能
        st.divider()
        search_query = st.text_input("🔍 キーワード検索", "")

    # --- フィルタリング処理 ---
    if filter_option == "✅ AI: 楽譜 (True)":
        display_df = df[df['is_score'] == True]
    elif filter_option == "❌ AI: 非楽譜 (False)":
        display_df = df[df['is_score'] == False]
    elif filter_option == "❓ AI: 不明 (Null)":
        display_df = df[df['is_score'].isnull()]
    else:
        display_df = df

    if search_query:
        cols = ['label'] + (['reason'] if 'reason' in display_df.columns else [])
        mask = display_df[cols].apply(lambda x: x.astype(str).str.contains(search_query, case=False)).any(axis=1)
        display_df = display_df[mask]

    st.markdown(f"**表示中: {len(display_df)} 件**")
    st.caption("右側の「人間判定」を変更すると、即座に記録されます。")
    st.divider()

    # --- リスト表示ループ ---
    # ページネーションなしで全件表示（件数が多い場合は重くなるので注意）
    # ※動作を軽くするため、上位200件ずつ表示するなどの制限を入れても良いですが、
    #  今回はスクロールで見たいとのことなのでそのまま出します。
    
    for index, row in display_df.iterrows():
        item_id = row['id']
        ai_val = row['is_score']
        
        # 現在の状態を取得（人間が変更していればそれ、なければAIの値）
        current_decision = st.session_state["human_decisions"].get(item_id, ai_val)
        
        # 状態に応じた背景色
        if current_decision == True:
            bg_style = "background-color: #e6fffa; padding: 10px; border-radius: 5px;" # 薄い緑
            status_icon = "✅ 楽譜"
        elif current_decision == False:
            bg_style = "background-color: #fff5f5; padding: 10px; border-radius: 5px;" # 薄い赤
            status_icon = "❌ 除外"
        else:
            bg_style = "padding: 10px;"
            status_icon = "❓ 不明"

        # --- 行のレイアウト ---
        # 3カラム: [AIの意見] - [タイトルと理由] - [人間の最終決定ボタン]
        c1, c2, c3 = st.columns([1, 4, 2])
        
        # 1. AIの意見 (固定表示)
        with c1:
            if ai_val == True:
                st.caption("🤖 AI判定")
                st.write(":green[**T (楽譜)**]")
            elif ai_val == False:
                st.caption("🤖 AI判定")
                st.write(":red[**F (除外)**]")
            else:
                st.caption("🤖 AI判定")
                st.write(":grey[**? (不明)**]")

        # 2. メイン情報
        with c2:
            st.markdown(f"#### {row['label']}")
            reason_text = row.get('reason', '')
            if reason_text:
                st.info(f"{reason_text}")
            else:
                st.caption("理由なし")
            st.caption(f"ID: {item_id}")

        # 3. 人間の修正インターフェース
        with c3:
            st.markdown("**人間の判定 (修正)**")
            
            # ラジオボタンで切り替え
            # keyにIDを含めて一意にする
            
            # 選択肢の定義
            options = [True, False]
            # 表示ラベルの定義
            format_func = lambda x: "✅ 楽譜にする" if x else "❌ 除外する"
            
            # None(Null)の場合のハンドリング
            idx = 0
            if current_decision == True: idx = 0
            if current_decision == False: idx = 1
            if current_decision is None: idx = 1 # デフォルトを除外にしておく等の処理
            
            new_decision = st.radio(
                "判定を選択:",
                options,
                format_func=format_func,
                index=idx,
                key=f"radio_{item_id}",
                horizontal=True,
                label_visibility="collapsed"
            )
            
            # 値が変わったらセッションに保存
            if new_decision != current_decision:
                st.session_state["human_decisions"][item_id] = new_decision
                # ※rerunすると画面がリセットされてスクロール位置が戻るため、
                #  ここではrerunせず、次回の操作反映を待つか、
                #  即座に色を変えたい場合は st.rerun() を入れる。
                #  (UX的にはrerunしないほうが連続操作しやすい)

        st.markdown("---") # 区切り線

else:
    st.error(f"ファイルが見つかりません: {INPUT_FILE}")