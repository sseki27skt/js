# -*- coding: utf-8 -*-
"""
人間による最終査読・手動オーバーライドポータル モジュール
"""

import json
import os
import pandas as pd


def load_merged_review_data(
    raw_jsonl_path: str,
    about_filtered_path: str,
    suffix_filtered_path: str,
    ngram_filtered_path: str,
    llm_judgments_path: str = None
) -> list:
    """
    全工程（About, 接尾辞, N-Gram, LLM判定）の結果を集約し、
    各資料の現在の判定ステータスと判定理由バッジが付与された統合査読データを返します。
    """
    if not os.path.exists(raw_jsonl_path):
        return []

    # 各フェーズの合格ID集合を作成
    about_passed_ids = set()
    if os.path.exists(about_filtered_path):
        with open(about_filtered_path, 'r', encoding='utf-8') as f:
            for line in f:
                if line.strip():
                    item = json.loads(line)
                    about_passed_ids.add(item.get("@id", ""))

    suffix_passed_ids = set()
    if os.path.exists(suffix_filtered_path):
        with open(suffix_filtered_path, 'r', encoding='utf-8') as f:
            for line in f:
                if line.strip():
                    item = json.loads(line)
                    suffix_passed_ids.add(item.get("@id", ""))

    ngram_passed_ids = set()
    if os.path.exists(ngram_filtered_path):
        with open(ngram_filtered_path, 'r', encoding='utf-8') as f:
            for line in f:
                if line.strip():
                    item = json.loads(line)
                    ngram_passed_ids.add(item.get("@id", ""))

    # LLM判定結果のマップ
    llm_map = {}
    if llm_judgments_path and os.path.exists(llm_judgments_path):
        with open(llm_judgments_path, 'r', encoding='utf-8') as f:
            for line in f:
                if line.strip():
                    j = json.loads(line)
                    llm_map[j.get("id", "")] = j

    merged_records = []

    with open(raw_jsonl_path, 'r', encoding='utf-8', errors='ignore') as f:
        for line in f:
            if not line.strip():
                continue
            item = json.loads(line)
            item_id = item.get("@id", "")

            label = item.get("rdfs:label", item.get("schema:name", "No Title"))
            title = label[0] if isinstance(label, list) and label else str(label)

            # 各フェーズでの判定ステータス評価
            is_about_ok = item_id in about_passed_ids if about_passed_ids else True
            is_suffix_ok = item_id in suffix_passed_ids if suffix_passed_ids else True
            is_ngram_ok = item_id in ngram_passed_ids if ngram_passed_ids else True
            
            llm_info = llm_map.get(item_id, {})
            llm_target = llm_info.get("is_target")
            llm_reason = llm_info.get("reason", "")

            # 総合初期判定
            final_status = "合格"
            reasons = []

            if not is_about_ok:
                final_status = "除外"
                reasons.append("Aboutルール除外")
            if not is_suffix_ok:
                final_status = "除外"
                reasons.append("接尾辞ルール除外")
            if not is_ngram_ok:
                final_status = "除外"
                reasons.append("N-Gramルール除外")

            if llm_target is False:
                final_status = "除外"
                reasons.append(f"LLM判定除外: {llm_reason}")
            elif llm_target is True:
                reasons.append(f"LLM判定適合: {llm_reason}")

            if not reasons:
                reasons.append("全ルール通過")

            merged_records.append({
                "id": item_id,
                "title": title,
                "status": final_status,
                "reasons": " / ".join(reasons),
                "is_about_ok": is_about_ok,
                "is_suffix_ok": is_suffix_ok,
                "is_ngram_ok": is_ngram_ok,
                "llm_target": llm_target,
                "llm_reason": llm_reason,
                "raw_item": item
            })

    return merged_records


def save_human_verified_data(records: list, human_decisions: dict, output_verified_jsonl: str) -> int:
    """
    人間が手動オーバーライド修正を行った最終確定データを jsonl へ保存します。
    human_decisions: {item_id: "合格" または "除外"}
    """
    os.makedirs(os.path.dirname(output_verified_jsonl), exist_ok=True)

    passed_count = 0
    with open(output_verified_jsonl, 'w', encoding='utf-8') as f:
        for r in records:
            item_id = r["id"]
            human_status = human_decisions.get(item_id, r["status"])
            
            if human_status == "合格":
                raw_item = r["raw_item"]
                raw_item["_human_verified"] = True
                raw_item["_final_status"] = "合格"
                f.write(json.dumps(raw_item, ensure_ascii=False) + "\n")
                passed_count += 1

    return passed_count
