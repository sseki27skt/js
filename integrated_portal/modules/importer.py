# -*- coding: utf-8 -*-
import os
import shutil

# 移行（インポート）対象のファイルマッピング
# (コピー元パス, コピー先パス)
ASSET_MAPPING = {
    # 収集データ
    "data/target_uris_classical_retry.csv": "integrated_portal/pipeline_steps/01_data_collection/target_uris.csv",
    "data/classical_scores_dynamic.jsonl": "integrated_portal/pipeline_steps/01_data_collection/raw_metadata.jsonl",
    
    # ルールベース
    "02_rule_based_filtering/about_rules.json": "integrated_portal/rules/about_rules.json",
    "02_rule_based_filtering/suffix_rules.json": "integrated_portal/rules/suffix_rules.json",
    
    # N-gram仕分けルール
    "fragments/ngram/ok_word_list.txt": "integrated_portal/rules/ok_word_list.txt",
    "fragments/ngram/ng_word_list.txt": "integrated_portal/rules/ng_word_list.txt",
    
    # 必要に応じて中間データも流用
    "data/classical_scores_about_filtered.jsonl": "integrated_portal/pipeline_steps/02_rule_based_filtering/about_filtered.jsonl",
    "data/classical_scores_suffix_filtered.jsonl": "integrated_portal/pipeline_steps/03_hybrid_classification/suffix_filtered.jsonl",
    
    # N-gram集計データ（手戻り発生時に再利用可能）
    "fragments/ngram/keyword_mining_ranking.csv": "integrated_portal/pipeline_steps/03_hybrid_classification/ngram_ranking.csv",
    "fragments/ngram/keyword_samples.json": "integrated_portal/pipeline_steps/03_hybrid_classification/ngram_samples.json",
}

def import_existing_assets(overwrite=False):
    """
    既存のデータおよびルールファイルを新環境（integrated_portal/）に安全にコピー（インポート）します。
    元ファイルは一切移動・変更・削除されません。
    """
    results = []
    
    for src, dest in ASSET_MAPPING.items():
        # コピー元が存在しない場合はスキップ
        if not os.path.exists(src):
            results.append({"file": src, "status": "skipped_not_found", "message": "元ファイルが存在しません。"})
            continue
            
        # コピー先ディレクトリの自動作成
        dest_dir = os.path.dirname(dest)
        os.makedirs(dest_dir, exist_ok=True)
        
        # コピー先がすでに存在し、上書き無効の場合はスキップ
        if os.path.exists(dest) and not overwrite:
            results.append({"file": dest, "status": "skipped_exists", "message": "インポート先に既に存在します（上書きスキップ）。"})
            continue
            
        try:
            # 安全に複製（メタデータも含めてコピー）
            shutil.copy2(src, dest)
            results.append({"file": dest, "status": "imported", "message": "正常にインポート（コピー）されました。"})
        except Exception as e:
            results.append({"file": dest, "status": "failed", "message": f"コピー失敗: {str(e)}"})
            
    return results

def get_import_status():
    """
    主要なデータ・ルールの新環境への移行状況をチェックします。
    """
    status = {}
    for src, dest in ASSET_MAPPING.items():
        key = os.path.basename(dest)
        status[key] = {
            "source_exists": os.path.exists(src),
            "dest_exists": os.path.exists(dest),
            "dest_path": dest
        }
    return status
