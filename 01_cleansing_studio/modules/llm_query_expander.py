# -*- coding: utf-8 -*-
"""
LLMアシスト型 網羅的検索キーワード拡張 & ドメイン定義生成モジュール (Gemini API / OpenAI / Local対応)
網羅性（Recall 100%志向）重視バージョン
"""

import json
import os
import re
import requests

DEFAULT_LLM_URL = os.environ.get("LLM_API_BASE", "http://localhost:1234/v1")
DEFAULT_MODEL = os.environ.get("LLM_MODEL", "local-model")


def expand_query_with_llm(
    theme_prompt: str, 
    provider: str = "local", 
    api_base: str = DEFAULT_LLM_URL, 
    api_key: str = "", 
    model: str = DEFAULT_MODEL
) -> dict:
    """
    ユーザーが入力したテーマから、Japan Searchからの網羅的取りこぼしゼロ収集用パラメータをLLMで超拡張・生成します。
    ノイズの混入を恐れず、異体字・旧字体・関連ジャンル・派生用語を徹底的にリストアップします。
    """
    system_prompt = (
        "あなたは日本の文化資源・人文学データの専門ライブラリアンおよびデータアナリストです。\n"
        "ユーザーが指定したテーマ・関心領域に基づき、Japan Searchから対象となり得る資料を【取りこぼしなく網羅的（Recall最大化）】に収集するための検索パラメータを生成してください。\n\n"
        "【最重要方針】:\n"
        "1. 後段のフィルタリング工程でノイズは除外するため、現段階ではノイズ（無関係な資料）の混入を全く気にする必要はありません。\n"
        "2. 対象テーマが含まれる可能性が少しでもある全ての【旧字体・異体字、派生語、専門用語、流派・楽器・形態名、関連周辺単語】を20〜40個以上徹底的に出力してください。\n"
        "3. キーワードは単一の長い文章ではなく、「譜」「楽譜」「樂譜」「音譜」「調子本」「謡本」「聲明譜」のように個別の単語リストとして出力してください。\n\n"
        "必ず以下の純粋で有効なJSONフォーマットのみを出力してください（コメントや説明文は不要です）：\n"
        "{\n"
        '  "theme": "テーマ名",\n'
        '  "domain_definition": "資料判定用ドメイン定義文",\n'
        '  "keywords": ["譜", "楽譜", "樂譜", "音譜", "譜面", "曲譜", "音律", "調子本", "謡本", "舞譜", "琴譜", "笛譜", "三味線譜", "聲明譜"],\n'
        '  "title_regex": "譜|楽譜|樂譜|音譜|譜面|曲譜|音律|調子本|謡本|舞譜|琴譜|笛譜|三味線譜|聲明譜",\n'
        '  "desc_regex": "譜|楽譜|樂譜|音譜|譜面|曲譜|音律|調子本|謡本|舞譜|琴譜|笛譜|三味線譜|聲明譜"\n'
        "}\n"
    )

    user_prompt = f"対象テーマ: {theme_prompt}"

    # --- 1. Google Gemini API 呼び出しロジック ---
    if provider.lower() == "gemini":
        gemini_key = api_key or os.environ.get("GEMINI_API_KEY", "")
        if not gemini_key:
            return _build_fallback_result(theme_prompt, "Gemini APIキーが設定されていません。")

        target_model = model if model and model != "local-model" else "gemini-3.6-flash"
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{target_model}:generateContent?key={gemini_key}"
        
        payload = {
            "contents": [
                {
                    "role": "user",
                    "parts": [{"text": f"{system_prompt}\n\n{user_prompt}"}]
                }
            ],
            "generationConfig": {
                "temperature": 0.3,
                "responseMimeType": "application/json"
            }
        }

        try:
            res = requests.post(url, json=payload, timeout=30)
            if res.status_code == 200:
                resp_json = res.json()
                text_content = resp_json["candidates"][0]["content"]["parts"][0]["text"]
                parsed = json.loads(text_content.strip())
                parsed["is_fallback"] = False
                parsed["fallback_reason"] = None
                return parsed
            else:
                return _build_fallback_result(theme_prompt, f"Gemini API エラー (Status {res.status_code}): {res.text[:200]}")
        except Exception as e:
            return _build_fallback_result(theme_prompt, f"Gemini API 接続例外: {e}")

    # --- 2. Local LLM / OpenAI 互換 API 呼び出しロジック ---
    else:
        req_headers = {"Content-Type": "application/json"}
        if api_key:
            req_headers["Authorization"] = f"Bearer {api_key}"

        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": f"/no_think\n思考は行わず直ちにJSONのみ出力してください。\n{system_prompt}"},
                {"role": "user", "content": user_prompt}
            ],
            "temperature": 0.2,
            "max_tokens": 4000
        }

        try:
            url = f"{api_base.rstrip('/')}/chat/completions"
            res = requests.post(url, json=payload, headers=req_headers, timeout=120)
            if res.status_code == 200:
                choice_msg = res.json()["choices"][0]["message"]
                content = choice_msg.get("content") or ""
                
                if not content.strip() and "reasoning_content" in choice_msg:
                    content = choice_msg.get("reasoning_content") or ""

                cleaned = re.sub(r"^```json\s*", "", content.strip(), flags=re.MULTILINE)
                cleaned = re.sub(r"^```\s*", "", cleaned, flags=re.MULTILINE)
                cleaned = re.sub(r"\s*```$", "", cleaned, flags=re.MULTILINE)
                cleaned = re.sub(r"//.*$", "", cleaned, flags=re.MULTILINE)

                json_match = re.search(r"\{.*\}", cleaned, re.DOTALL)
                if json_match:
                    cleaned = json_match.group(0)

                parsed = json.loads(cleaned)
                parsed["is_fallback"] = False
                parsed["fallback_reason"] = None
                return parsed
            else:
                return _build_fallback_result(theme_prompt, f"APIエラー Status {res.status_code}: {res.text[:200]}")
        except Exception as e:
            return _build_fallback_result(theme_prompt, f"API接続エラー: {e}")


def _build_fallback_result(theme_prompt: str, reason: str) -> dict:
    """フォールバックルールベース結果の構築"""
    print(f"[LLM Expander] フォールバック適用: {reason}")
    if any(k in theme_prompt for k in ["楽譜", "音楽", "譜"]):
        keywords = [
            "譜", "楽譜", "樂譜", "音譜", "譜面", "曲譜", "音律", "調子", "調子本",
            "謡本", "舞譜", "琴譜", "笛譜", "三味線譜", "聲明譜", "節用", "唱歌", "節付"
        ]
        title_regex = "|".join(keywords)
        desc_regex = title_regex
    else:
        words = [w.strip() for w in re.split(r"[\s,・/／におけるについて]+", theme_prompt) if len(w.strip()) >= 2]
        keywords = words if words else [theme_prompt]
        title_regex = "|".join(keywords)
        desc_regex = title_regex

    return {
        "theme": theme_prompt,
        "domain_definition": f"「{theme_prompt}」に関連する文化資源・文献・資料",
        "keywords": keywords,
        "title_regex": title_regex,
        "desc_regex": desc_regex,
        "is_fallback": True,
        "fallback_reason": reason
    }


def generate_sparql_queries(expansion_result: dict) -> list:
    """
    SPARQLクエリ一覧の自動生成 (Recall 最大化仕様)
    - rdf:type 絞り込みを排除し全RDFリソースを検索。
    - rdfs:label, schema:name, schema:about, schema:keywords, dct:subject, schema:description を網羅化。
    - NDC 検索は撤廃。
    """
    title_regex = expansion_result.get("title_regex", "")
    desc_regex = expansion_result.get("desc_regex", title_regex)
    
    queries = []
    
    # 1. タイトル・名称 (rdfs:label | schema:name) 検索
    if title_regex:
        def q_title(lim, last_uri=None):
            f_clause = f"FILTER (?s > <{last_uri}>)" if last_uri else ""
            return f"""
            PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
            PREFIX schema: <http://schema.org/>
            
            SELECT DISTINCT ?s WHERE {{
              ?s (rdfs:label|schema:name) ?title .
              FILTER (REGEX(?title, "{title_regex}", "i"))
              {f_clause}
            }}
            ORDER BY ?s
            LIMIT {lim}
            """
        queries.append(("1. タイトル・名称 (label / name) 網羅検索", q_title))

    # 2. 主題・件名・キーワード (schema:about | schema:keywords | dct:subject) 検索
    if title_regex:
        def q_subject(lim, last_uri=None):
            f_clause = f"FILTER (?s > <{last_uri}>)" if last_uri else ""
            return f"""
            PREFIX schema: <http://schema.org/>
            PREFIX dct: <http://purl.org/dc/terms/>
            
            SELECT DISTINCT ?s WHERE {{
              ?s (schema:about|schema:keywords|dct:subject) ?sub .
              FILTER (REGEX(STR(?sub), "{title_regex}", "i"))
              {f_clause}
            }}
            ORDER BY ?s
            LIMIT {lim}
            """
        queries.append(("2. 主題・件名・キーワード (about / keywords / subject) 網羅検索", q_subject))

    # 3. 説明文・内容記述 (schema:description) 検索
    if desc_regex:
        def q_desc(lim, last_uri=None):
            f_clause = f"FILTER (?s > <{last_uri}>)" if last_uri else ""
            return f"""
            PREFIX schema: <http://schema.org/>
            
            SELECT DISTINCT ?s WHERE {{
              ?s schema:description ?desc .
              FILTER (REGEX(?desc, "{desc_regex}", "i"))
              {f_clause}
            }}
            ORDER BY ?s
            LIMIT {lim}
            """
        queries.append(("3. 説明文 (description) 網羅検索", q_desc))

    return queries
