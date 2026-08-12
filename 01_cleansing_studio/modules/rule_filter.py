# -*- coding: utf-8 -*-
"""
ルールベースフィルタ (About/接尾辞) モジュール ＋ LLMキーワードサジェスト機能 (Gemini API / OpenAI / Local対応)
"""

import json
import os
import re
import urllib.parse
import requests
from collections import Counter

DEFAULT_LLM_URL = os.environ.get("LLM_API_BASE", "http://localhost:1234/v1")
DEFAULT_MODEL = os.environ.get("LLM_MODEL", "local-model")


def extract_about_values(about_val) -> list:
    """
    schema:about の生表現（str, dict, list, またはそのネスト）から
    キーワード名 / URL解読名の一覧をリストとして抽出します。
    """
    if not about_val:
        return []
    
    raw_list = about_val if isinstance(about_val, list) else [about_val]
    keywords = []
    
    for item in raw_list:
        if not item:
            continue
        if isinstance(item, dict):
            val = item.get("rdfs:label") or item.get("schema:name") or item.get("@id") or ""
            if isinstance(val, list) and val:
                val = val[0]
            val_str = str(val).strip()
        else:
            val_str = str(item).strip()
            
        if not val_str:
            continue
            
        if val_str.startswith("http"):
            kw_name = urllib.parse.unquote(val_str.split("/")[-1])
            if kw_name:
                keywords.append(kw_name)
        else:
            keywords.append(val_str)
            
    return keywords


def extract_about_keywords_from_jsonl(input_jsonl_path: str) -> list:
    """
    raw_metadata.jsonl から schema:about のキーワードを抽出・カウント集計し、
    [(キーワード, 出現件数), ...] の降順リストとして返します。
    """
    if not os.path.exists(input_jsonl_path):
        return []

    counter = Counter()

    with open(input_jsonl_path, 'r', encoding='utf-8', errors='ignore') as f:
        for line in f:
            if not line.strip():
                continue
            try:
                item = json.loads(line)
                about_val = item.get("schema:about", [])
                for kw in extract_about_values(about_val):
                    counter[kw] += 1
            except Exception:
                continue

    return counter.most_common()


def extract_suffixes_from_jsonl(input_jsonl_path: str, max_suffix_len: int = 3) -> list:
    """
    raw_metadata.jsonl からタイトルの末尾語彙 (接尾辞: 〜譜, 〜本, 〜録など) を抽出・カウント集計し、
    [(接尾辞, 出現件数), ...] の降順リストとして返します。
    """
    if not os.path.exists(input_jsonl_path):
        return []

    counter = Counter()

    with open(input_jsonl_path, 'r', encoding='utf-8', errors='ignore') as f:
        for line in f:
            if not line.strip():
                continue
            try:
                item = json.loads(line)
                label_val = item.get("rdfs:label", item.get("schema:name", ""))
                if isinstance(label_val, list) and label_val:
                    label_str = str(label_val[0]).strip()
                else:
                    label_str = str(label_val).strip()

                if label_str:
                    clean_label = re.sub(r"[\s\(\)（）\[\]【】\d]+$", "", label_str)
                    if clean_label:
                        for l in range(1, max_suffix_len + 1):
                            if len(clean_label) >= l:
                                suf = clean_label[-l:]
                                counter[suf] += 1
            except Exception:
                continue

    return counter.most_common()


def suggest_ng_keywords_with_llm(
    current_ng_list: list, 
    sample_keywords: list, 
    target_keywords: list = None, 
    domain_definition: str = "", 
    provider: str = "local",
    api_base: str = DEFAULT_LLM_URL,
    api_key: str = "",
    model: str = DEFAULT_MODEL
) -> list:
    """
    【Gemini API / Local / OpenAI対応 高速ノイズサジェスト】
    目的キーワードと『無関係・異分野』なノイズ単語候補をデータセットから逆引き分析して選別・提案します。
    """
    if target_keywords is None:
        target_keywords = []

    sample_targets = target_keywords[:15]
    sample_ngs = current_ng_list[-20:] if len(current_ng_list) > 20 else current_ng_list
    sample_kws = sample_keywords[:40]

    system_prompt = (
        "あなたは文化資源メタデータの精査アシスタントです。\n"
        "ユーザーが提示した『目的キーワード』と『サンプル単語群』を比較し、"
        "目的キーワードのドメイン・ジャンルと【無関係・異分野】であると判断されるノイズ（除外対象）キーワード候補を25個程度選んで提案してください。\n"
        "出力は必ず純粋なJSON配列形式（例: [\"単語1\", \"単語2\"]）のみとしてください。"
    )

    user_prompt = (
        f"【目的キーワード】: {', '.join(sample_targets)}\n"
        f"【既知のNG例】: {', '.join(sample_ngs)}\n"
        f"【サンプル単語群】: {', '.join(sample_kws)}\n\n"
        "上記を踏まえ、無関係なノイズキーワード候補をJSON配列で返してください。"
    )

    ng_set = set(current_ng_list)
    ok_set = set(target_keywords)

    # --- 1. Google Gemini API ---
    if provider.lower() == "gemini":
        gemini_key = api_key or os.environ.get("GEMINI_API_KEY", "")
        if not gemini_key:
            return [k for k in sample_keywords if k not in ng_set and k not in ok_set][:15]

        target_model = model if model and model != "local-model" else "gemini-3.6-flash"
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{target_model}:generateContent?key={gemini_key}"

        payload = {
            "contents": [{
                "role": "user",
                "parts": [{"text": f"{system_prompt}\n\n{user_prompt}"}]
            }],
            "generationConfig": {
                "temperature": 0.1,
                "responseMimeType": "application/json"
            }
        }

        try:
            res = requests.post(url, json=payload, timeout=20)
            if res.status_code == 200:
                resp_json = res.json()
                text_content = resp_json["candidates"][0]["content"]["parts"][0]["text"]
                parsed = json.loads(text_content.strip())
                if isinstance(parsed, list):
                    return [k for k in parsed if k not in ng_set and k not in ok_set]
        except Exception as e:
            print(f"[Gemini Suggest Warning] {e}")

    # --- 2. Local LLM / OpenAI ---
    else:
        req_headers = {"Content-Type": "application/json"}
        if api_key:
            req_headers["Authorization"] = f"Bearer {api_key}"

        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": f"/no_think\n{system_prompt}"},
                {"role": "user", "content": user_prompt}
            ],
            "temperature": 0.0,
            "max_tokens": 1000
        }

        try:
            url = f"{api_base.rstrip('/')}/chat/completions"
            res = requests.post(url, json=payload, headers=req_headers, timeout=30)
            if res.status_code == 200:
                choice_msg = res.json()["choices"][0]["message"]
                content = choice_msg.get("content") or ""
                if not content.strip() and "reasoning_content" in choice_msg:
                    content = choice_msg.get("reasoning_content") or ""

                cleaned = re.sub(r"^```json\s*", "", content.strip(), flags=re.MULTILINE)
                cleaned = re.sub(r"^```\s*", "", cleaned, flags=re.MULTILINE)
                cleaned = re.sub(r"\s*```$", "", cleaned, flags=re.MULTILINE)

                json_match = re.search(r"\[.*\]", cleaned, re.DOTALL)
                if json_match:
                    cleaned = json_match.group(0)

                parsed = json.loads(cleaned)
                if isinstance(parsed, list):
                    return [k for k in parsed if k not in ng_set and k not in ok_set]
        except Exception as e:
            print(f"[LLM Fast Suggest Warning] {e}")

    return [k for k in sample_keywords if k not in ng_set and k not in ok_set][:15]


def suggest_related_keywords_by_base(
    base_keyword: str, 
    mode: str, 
    sample_keywords: list, 
    provider: str = "local",
    api_base: str = DEFAULT_LLM_URL,
    api_key: str = "",
    model: str = DEFAULT_MODEL
) -> list:
    """
    【Gemini API / Local / OpenAI対応 3点メニュー連想提案】
    特定の単一キーワード (base_keyword) を起点として、関連するノイズ(NG)または保持(OK)単語をGemini等で1秒サジェストします。
    """
    prioritized_kws = []
    other_kws = []
    base_chars = set(base_keyword)

    for kw in sample_keywords:
        if kw == base_keyword:
            continue
        if any(c in kw for c in base_chars if len(base_keyword) <= 2 or c not in "歴史研究図書"):
            prioritized_kws.append(kw)
        else:
            other_kws.append(kw)

    candidate_samples = (prioritized_kws + other_kws)[:30]

    if mode == "ng":
        mode_instruction = f"キーワード『{base_keyword}』と同類・類似する非対象（ノイズ）キーワード"
    else:
        mode_instruction = f"キーワード『{base_keyword}』と同一ジャンル・関連する保持キーワード"

    system_prompt = (
        "あなたは文化資源メタデータの精査アシスタントです。\n"
        f"提示されたサンプルの中から、{mode_instruction}を10個程度選んで提案してください。\n"
        "出力は必ず純粋なJSON配列形式（例: [\"単語1\", \"単語2\"]）のみとしてください。"
    )

    user_prompt = (
        f"【起点キーワード】: {base_keyword}\n"
        f"【サンプル単語群】: {', '.join(candidate_samples)}\n\n"
        f"{mode_instruction}をJSON配列で返してください。"
    )

    # --- 1. Google Gemini API ---
    if provider.lower() == "gemini":
        gemini_key = api_key or os.environ.get("GEMINI_API_KEY", "")
        if not gemini_key:
            return [kw for kw in candidate_samples if base_keyword != kw][:8]

        target_model = model if model and model != "local-model" else "gemini-3.6-flash"
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{target_model}:generateContent?key={gemini_key}"

        payload = {
            "contents": [{
                "role": "user",
                "parts": [{"text": f"{system_prompt}\n\n{user_prompt}"}]
            }],
            "generationConfig": {
                "temperature": 0.1,
                "responseMimeType": "application/json"
            }
        }

        try:
            res = requests.post(url, json=payload, timeout=15)
            if res.status_code == 200:
                resp_json = res.json()
                text_content = resp_json["candidates"][0]["content"]["parts"][0]["text"]
                parsed = json.loads(text_content.strip())
                if isinstance(parsed, list):
                    return [k for k in parsed if k != base_keyword]
        except Exception as e:
            print(f"[Gemini Base Suggest Warning] {e}")

    # --- 2. Local LLM / OpenAI ---
    else:
        req_headers = {"Content-Type": "application/json"}
        if api_key:
            req_headers["Authorization"] = f"Bearer {api_key}"

        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": f"/no_think\n{system_prompt}"},
                {"role": "user", "content": user_prompt}
            ],
            "temperature": 0.0,
            "max_tokens": 800
        }

        try:
            url = f"{api_base.rstrip('/')}/chat/completions"
            res = requests.post(url, json=payload, headers=req_headers, timeout=20)
            if res.status_code == 200:
                choice_msg = res.json()["choices"][0]["message"]
                content = choice_msg.get("content") or ""
                if not content.strip() and "reasoning_content" in choice_msg:
                    content = choice_msg.get("reasoning_content") or ""

                cleaned = re.sub(r"^```json\s*", "", content.strip(), flags=re.MULTILINE)
                cleaned = re.sub(r"^```\s*", "", cleaned, flags=re.MULTILINE)
                cleaned = re.sub(r"\s*```$", "", cleaned, flags=re.MULTILINE)

                json_match = re.search(r"\[.*\]", cleaned, re.DOTALL)
                if json_match:
                    cleaned = json_match.group(0)

                parsed = json.loads(cleaned)
                if isinstance(parsed, list):
                    return [k for k in parsed if k != base_keyword]
        except Exception as e:
            print(f"[LLM Base Fast Suggest Warning] {e}")

    return [kw for kw in candidate_samples if base_keyword != kw][:8]


def run_about_filter(input_jsonl_path: str, rules_json_path: str, output_filtered_path: str, output_discarded_csv: str):
    """schema:about キーワード分類ルールに基づいてデータをフィルタリング"""
    if not os.path.exists(input_jsonl_path):
        return 0, 0

    about_rules = {}
    if os.path.exists(rules_json_path):
        with open(rules_json_path, 'r', encoding='utf-8') as f:
            about_rules = json.load(f)

    ng_categories = set([cat for cat, status in about_rules.items() if status == "NG"])

    passed_count = 0
    discarded_records = []

    os.makedirs(os.path.dirname(output_filtered_path), exist_ok=True)
    os.makedirs(os.path.dirname(output_discarded_csv), exist_ok=True)

    with open(input_jsonl_path, 'r', encoding='utf-8') as in_f, \
         open(output_filtered_path, 'w', encoding='utf-8') as out_f:

        for line in in_f:
            if not line.strip():
                continue
            item = json.loads(line)
            
            about_val = item.get("schema:about", [])
            extracted_kws = extract_about_values(about_val)

            has_ng = False
            matched_ng_cat = ""
            for kw in extracted_kws:
                for ng_cat in ng_categories:
                    if ng_cat in kw:
                        has_ng = True
                        matched_ng_cat = ng_cat
                        break
                if has_ng:
                    break

            if has_ng:
                label = item.get("rdfs:label", item.get("schema:name", "No Title"))
                discarded_records.append({
                    "id": item.get("@id", ""),
                    "title": label if isinstance(label, str) else str(label),
                    "matched_ng": matched_ng_cat,
                    "reason": f"Aboutルール除外: {matched_ng_cat}"
                })
            else:
                out_f.write(json.dumps(item, ensure_ascii=False) + "\n")
                passed_count += 1

    if discarded_records:
        import pandas as pd
        df_disc = pd.DataFrame(discarded_records)
        df_disc.to_csv(output_discarded_csv, index=False, encoding='utf-8-sig')

    return passed_count, len(discarded_records)


def run_suffix_filter(input_jsonl_path: str, rules_json_path: str, output_filtered_path: str, output_discarded_csv: str):
    """末尾語彙（接尾辞）ルールに基づいてノイズタイトルを除外"""
    if not os.path.exists(input_jsonl_path):
        return 0, 0

    suffix_rules = {}
    if os.path.exists(rules_json_path):
        with open(rules_json_path, 'r', encoding='utf-8') as f:
            suffix_rules = json.load(f)

    ng_suffixes = set([suf for suf, status in suffix_rules.items() if status == "NG"])

    passed_count = 0
    discarded_records = []

    os.makedirs(os.path.dirname(output_filtered_path), exist_ok=True)
    os.makedirs(os.path.dirname(output_discarded_csv), exist_ok=True)

    with open(input_jsonl_path, 'r', encoding='utf-8') as in_f, \
         open(output_filtered_path, 'w', encoding='utf-8') as out_f:

        for line in in_f:
            if not line.strip():
                continue
            item = json.loads(line)
            
            label_val = item.get("rdfs:label", item.get("schema:name", ""))
            if isinstance(label_val, list) and label_val:
                label_str = str(label_val[0])
            else:
                label_str = str(label_val)

            has_ng = False
            matched_suffix = ""
            for suf in ng_suffixes:
                if label_str.endswith(suf):
                    has_ng = True
                    matched_suffix = suf
                    break

            if has_ng:
                discarded_records.append({
                    "id": item.get("@id", ""),
                    "title": label_str,
                    "matched_suffix": matched_suffix,
                    "reason": f"接尾辞ルール除外: 末尾「{matched_suffix}」"
                })
            else:
                out_f.write(json.dumps(item, ensure_ascii=False) + "\n")
                passed_count += 1

    if discarded_records:
        import pandas as pd
        df_disc = pd.DataFrame(discarded_records)
        df_disc.to_csv(output_discarded_csv, index=False, encoding='utf-8-sig')

    return passed_count, len(discarded_records)
