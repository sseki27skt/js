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

# 日本十進分類法 (NDC) 二次区分マスター辞書 (00-99)
NDC_MASTER = {
    "00": "00:総記", "01": "01:図書館・図書館情報学", "02": "02:図書・書誌学", "03": "03:百科事典", "04": "04:一般論文集",
    "05": "05:逐次刊行物", "06": "06:団体・博物館", "07": "07:ジャーナリズム・新聞", "08": "08:叢書・全集", "09": "09:貴重書・郷土資料",
    "10": "10:哲学", "11": "11:哲学各論", "12": "12:東洋哲学", "13": "13:西洋哲学", "14": "14:心理学",
    "15": "15:倫理学・道徳", "16": "16:宗教", "17": "17:神道", "18": "18:仏教", "19": "19:キリスト教",
    "20": "20:歴史・文化史", "21": "21:日本史", "22": "22:アジア史", "23": "23:ヨーロッパ史", "24": "24:アフリカ史",
    "25": "25:北アメリカ史", "26": "26:南アメリカ史", "27": "27:オセアニア史", "28": "28:伝記", "29": "29:地理・地誌・紀行",
    "30": "30:社会科学", "31": "31:政治", "32": "32:法律", "33": "33:経済", "34": "34:財政",
    "35": "35:統計", "36": "36:社会", "37": "37:教育", "38": "38:風俗習慣・民俗学", "39": "39:国防・軍事",
    "40": "40:自然科学", "41": "41:数学", "42": "42:物理学", "43": "43:化学", "44": "44:天文学",
    "45": "45:地球科学", "46": "46:生物科学", "47": "47:植物学", "48": "48:動物学", "49": "49:医学・薬学",
    "50": "50:技術・工学", "51": "51:建設・土木", "52": "52:建築学", "53": "53:機械工学", "54": "54:電気工学",
    "55": "55:海洋・軍事工学", "56": "56:金属・鉱山", "57": "57:化学工業", "58": "58:製造工業", "59": "59:家政学",
    "60": "60:産業", "61": "61:農業", "62": "62:園芸", "63": "63:蚕糸業", "64": "64:畜産業",
    "65": "65:林業", "66": "66:水産業", "67": "67:商業", "68": "68:運輸・交通・観光", "69": "69:通信事業",
    "70": "70:芸術・美術", "71": "71:彫刻", "72": "72:絵画・書道", "73": "73:版画・印章・印譜", "74": "74:写真・印刷",
    "75": "75:工芸", "76": "76:音楽・舞踊", "77": "77:演劇・映画・大衆芸能", "78": "78:スポーツ", "79": "79:諸芸・娯楽",
    "80": "80:言語", "81": "81:日本語", "82": "82:中国語・東洋諸語", "83": "83:英語", "84": "84:ドイツ語",
    "85": "85:フランス語", "86": "86:スペイン・ポルトガル語", "87": "87:イタリア語", "88": "88:ロシア語", "89": "89:その他言語",
    "90": "90:文学", "91": "91:日本文学", "92": "92:中国文学・東洋文学", "93": "93:英米文学", "94": "94:ドイツ文学",
    "95": "95:フランス文学", "96": "96:スペイン文学", "97": "97:イタリア文学", "98": "98:ロシア文学", "99": "99:その他文学"
}


def ndc_codes_to_labels(codes: list) -> list:
    """コードリスト (例: ['76', '77']) を表示ラベル表記のリスト (例: ['76:音楽・舞踊', ...]) に変換"""
    labels = []
    if not isinstance(codes, list):
        return labels
    for c in codes:
        raw_c = str(c).strip()
        code_str = raw_c.zfill(2) if raw_c.isdigit() and len(raw_c) <= 2 else raw_c
        if code_str in NDC_MASTER:
            labels.append(NDC_MASTER[code_str])
        elif raw_c:
            labels.append(raw_c)
    return labels


def ndc_labels_to_codes(labels: list) -> list:
    """表示ラベル表記のリストから 2桁の NDC コードリストを抽出"""
    codes = []
    if not isinstance(labels, list):
        return codes
    for label in labels:
        label_str = str(label).strip()
        if ":" in label_str:
            code_part = label_str.split(":")[0].strip()
            codes.append(code_part)
        elif label_str:
            codes.append(label_str)
    return codes


def _safe_json_loads(text_content: str) -> dict:
    """
    LLMが生成したJSON文字列から不要なマークダウン記法やコメントを除去し、
    生の改行・制御文字 (Invalid control character) を許容して安全にパースします。
    """
    if not text_content:
        raise ValueError("LLMからの応答テキストが空です")

    cleaned = re.sub(r"^```json\s*", "", text_content.strip(), flags=re.MULTILINE)
    cleaned = re.sub(r"^```\s*", "", cleaned, flags=re.MULTILINE)
    cleaned = re.sub(r"\s*```$", "", cleaned, flags=re.MULTILINE)
    cleaned = re.sub(r"//.*$", "", cleaned, flags=re.MULTILINE)

    json_match = re.search(r"\{.*\}", cleaned, re.DOTALL)
    if json_match:
        cleaned = json_match.group(0)

    try:
        return json.loads(cleaned, strict=False)
    except json.JSONDecodeError:
        cleaned_escaped = re.sub(
            r'[\x00-\x1f\x7f-\x9f]', 
            lambda m: '\\n' if m.group(0) == '\n' else ('\\t' if m.group(0) == '\t' else ''), 
            cleaned
        )
        return json.loads(cleaned_escaped, strict=False)


def expand_query_with_llm(
    theme_prompt: str, 
    provider: str = "local", 
    api_base: str = DEFAULT_LLM_URL, 
    api_key: str = "", 
    model: str = DEFAULT_MODEL
) -> dict:
    """
    ユーザーが指定したテーマに基づき、Japan Searchからの再現率（Recall）最大化を目的とした検索クエリ拡張パラメータをLLMを用いて自動生成します。
    対象ドメインに関連する異体字・旧字体・専門用語・周辺概念を体系的に抽出します。
    検索キーワード一覧 (keywords) を基盤に、正規表現パターン (title_regex, desc_regex) を自動生成します。
    """
    system_prompt = (
        "あなたは日本の文化資源・人文学データの専門ライブラリアンおよびデータアナリストです。\n"
        "ユーザーが指定したテーマ・関心領域に基づき、Japan Searchから対象となり得る資料を【漏れなく網羅的（Recall最大化）】に収集するための検索パラメータを生成してください。\n\n"
        "【最重要方針】:\n"
        "1. 後段のフィルタリング工程でノイズは除外するため、現段階ではノイズ（無関係な資料）の混入を全く気にする必要はありません。\n"
        "2. 対象テーマが含まれる可能性が少しでもある全ての【旧字体・異体字、派生語、専門用語、流派・楽器・形態名、関連周辺単語】を20〜40個以上徹底的に出力してください。\n"
        "3. キーワードは単一の長い文章ではなく、「譜」「楽譜」「樂譜」「音譜」「調子本」「謡本」「聲明譜」のように個別の単語リスト (keywords) として出力してください。\n"
        "4. title_regex および desc_regex には、keywords リストに含まれるすべてのキーワードを '|'（パイプ）で結合した REGEX パターンを出力してください。\n"
        "5. 対象テーマに関連するNDC（日本十進分類法）分類コードを、下記「NDC 二次区分一覧表」を参照して【2桁の分類記号（二次区分）】（例: [\"76\", \"77\", \"18\"]）で漏れなく特定し、ndc_codes リストに出力してください。\n\n"
        "【NDC (日本十進分類法) 二次区分一覧表】:\n"
        "00:総記, 01:図書館・図書館情報学, 02:図書・書誌学, 03:百科事典, 04:一般論文集, 05:逐次刊行物, 06:団体・博物館, 07:ジャーナリズム・新聞, 08:叢書・全集, 09:貴重書・郷土資料\n"
        "10:哲学, 11:哲学各論, 12:東洋哲学, 13:西洋哲学, 14:心理学, 15:倫理学・道徳, 16:宗教, 17:神道, 18:仏教, 19:キリスト教\n"
        "20:歴史・文化史, 21:日本史, 22:アジア史, 23:ヨーロッパ史, 24:アフリカ史, 25:北アメリカ史, 26:南アメリカ史, 27:オセアニア史, 28:伝記, 29:地理・地誌・紀行\n"
        "30:社会科学, 31:政治, 32:法律, 33:経済, 34:財政, 35:統計, 36:社会, 37:教育, 38:風俗習慣・民俗学, 39:国防・軍事\n"
        "40:自然科学, 41:数学, 42:物理学, 43:化学, 44:天文学, 45:地球科学, 46:生物科学, 47:植物学, 48:動物学, 49:医学・薬学\n"
        "50:技術・工学, 51:建設・土木, 52:建築学, 53:機械工学, 54:電気工学, 55:海洋・軍事工学, 56:金属・鉱山, 57:化学工業, 58:製造工業, 59:家政学\n"
        "60:産業, 61:農業, 62:園芸, 63:蚕糸業, 64:畜産業, 65:林業, 66:水産業, 67:商業, 68:運輸・交通・観光, 69:通信事業\n"
        "70:芸術・美術, 71:彫刻, 72:絵画・書道, 73:版画・印章・印譜, 74:写真・印刷, 75:工芸, 76:音楽・舞踊, 77:演劇・映画・大衆芸能, 78:スポーツ, 79:諸芸・娯楽\n"
        "80:言語, 81:日本語, 82:中国語・東洋諸語, 83:英語, 84:ドイツ語, 85:フランス語, 86:スペイン・ポルトガル語, 87:イタリア語, 88:ロシア語, 89:その他言語\n"
        "90:文学, 91:日本文学, 92:中国文学・東洋文学, 93:英米文学, 94:ドイツ文学, 95:フランス文学, 96:スペイン文学, 97:イタリア文学, 98:ロシア文学, 99:その他文学\n\n"
        "必ず以下の純粋で有効なJSONフォーマットのみを出力してください（コメントや説明文は不要です）：\n"
        "{\n"
        '  "theme": "テーマ名",\n'
        '  "domain_definition": "資料判定用ドメイン定義文",\n'
        '  "keywords": ["譜", "楽譜", "樂譜", "音譜", "譜面", "曲譜", "音律", "調子本", "謡本", "舞譜", "琴譜", "笛譜", "三味線譜", "聲明譜"],\n'
        '  "ndc_codes": ["76", "77", "18"],\n'
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
                resp_json = json.loads(res.text, strict=False)
                text_content = resp_json["candidates"][0]["content"]["parts"][0]["text"]
                parsed = _safe_json_loads(text_content)
                parsed["is_fallback"] = False
                parsed["fallback_reason"] = None
                return _sanitize_and_sync_result(parsed)
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
            res = requests.post(url, json=payload, headers=req_headers, timeout=6000)
            if res.status_code == 200:
                resp_json = json.loads(res.text, strict=False)
                choice_msg = resp_json["choices"][0]["message"]
                content = choice_msg.get("content") or ""
                
                if not content.strip() and "reasoning_content" in choice_msg:
                    content = choice_msg.get("reasoning_content") or ""

                parsed = _safe_json_loads(content)
                parsed["is_fallback"] = False
                parsed["fallback_reason"] = None
                return _sanitize_and_sync_result(parsed)
            else:
                return _build_fallback_result(theme_prompt, f"APIエラー Status {res.status_code}: {res.text[:200]}")
        except Exception as e:
            return _build_fallback_result(theme_prompt, f"API接続エラー: {e}")


def optimize_keywords_for_regex(keywords: list[str]) -> list[str]:
    """
    部分文字列として包含される冗長なキーワードを除外して正規表現用キーワードリストを最適化
    例: ['譜', '楽譜', '音譜', '調子本'] -> ['譜', '調子本']
    """
    cleaned = [str(k).strip() for k in keywords if str(k).strip()]
    sorted_kws = sorted(list(set(cleaned)), key=len)
    optimized = []
    for kw in sorted_kws:
        if not any(short_kw in kw for short_kw in optimized):
            optimized.append(kw)
    return optimized


def optimize_regex_str(regex_str: str) -> str:
    """
    パイプ区切りの正規表現文字列を受け取り、包含関係にある冗長キーワードを除去して最適化
    丸かっこ () や角かっこ [] などの余分な包み込み記号を除去します
    """
    if not regex_str or not isinstance(regex_str, str):
        return ""
    # 文字列全体から丸かっこ・角かっこ・波かっこ・クォートを除去
    cleaned_str = re.sub(r"[\(\)\[\]\{\}\"']", "", regex_str)
    
    kws = [k.strip() for k in cleaned_str.split("|") if k.strip()]
    optimized = optimize_keywords_for_regex(kws)
    return "|".join(optimized)


def chunk_regex_str(regex_str: str, chunk_size: int = 12) -> list[str]:
    """
    パイプ区切りの REGEX 文字列を受け取り、指定サイズ (デフォルト12語) ごとの安全な REGEX 文字列リストに分割する
    Japan Search SPARQL サーバーでの 504 Gateway Timeout を物理的に回避します
    """
    if not regex_str or not isinstance(regex_str, str):
        return []
    cleaned_str = re.sub(r"[\(\)\[\]\{\}\"']", "", regex_str)
    kws = [k.strip() for k in cleaned_str.split("|") if k.strip()]
    opt_kws = optimize_keywords_for_regex(kws)
    if not opt_kws:
        return []

    chunked = []
    for i in range(0, len(opt_kws), chunk_size):
        sub_group = opt_kws[i:i + chunk_size]
        chunked.append("|".join(sub_group))
    return chunked


def _sanitize_and_sync_result(result: dict) -> dict:
    """keywords から title_regex および desc_regex を自動連動・確認・補正（包含関係の最適化含む）"""
    if "keywords" in result and isinstance(result["keywords"], list):
        kws = [str(k).strip() for k in result["keywords"] if str(k).strip()]
        result["keywords"] = kws
        
        # keywords から包含関係を除外した最適化済み REGEX パターンを作成
        optimized_kws = optimize_keywords_for_regex(kws)
        auto_regex = "|".join(optimized_kws)
        
        if not result.get("title_regex"):
            result["title_regex"] = auto_regex
        else:
            result["title_regex"] = optimize_regex_str(result["title_regex"])

        if not result.get("desc_regex"):
            result["desc_regex"] = auto_regex
        else:
            result["desc_regex"] = optimize_regex_str(result["desc_regex"])
    else:
        if result.get("title_regex"):
            result["title_regex"] = optimize_regex_str(result["title_regex"])
        if result.get("desc_regex"):
            result["desc_regex"] = optimize_regex_str(result["desc_regex"])

    return result


def _build_fallback_result(theme_prompt: str, reason: str) -> dict:
    """フォールバックルールベース結果の構築（ドメイン固定コードを排除し汎用化）"""
    print(f"[LLM Expander] フォールバック適用: {reason}")
    words = [w.strip() for w in re.split(r"[\s,・/／におけるについて等の文献資料]+", theme_prompt) if len(w.strip()) >= 2]
    keywords = words if words else [theme_prompt]
    ndc_codes = []

    opt_kws = optimize_keywords_for_regex(keywords)
    title_regex = "|".join(opt_kws)
    desc_regex = title_regex

    return {
        "theme": theme_prompt,
        "domain_definition": f"「{theme_prompt}」に関連する文化資源・文献・資料",
        "keywords": keywords,
        "ndc_codes": ndc_codes,
        "title_regex": title_regex,
        "desc_regex": desc_regex,
        "is_fallback": True,
        "fallback_reason": reason
    }


def generate_sparql_queries(expansion_result: dict) -> list:
    """
    SPARQLクエリ一覧の自動生成 (Recall 最大化 ＆ 504 Timeout 回避チャンク分割仕様)
    - rdf:type 絞り込みを排除し全RDFリソースを検索。
    - rdfs:label, schema:name, schema:about, schema:keywords, dct:subject, schema:description を網羅化。
    - REGEXパターン長を12語ごとに自動分割し、Virtuosoサーバーの504 Timeoutを完全に回避。
    """
    raw_title_regex = expansion_result.get("title_regex", "")
    raw_desc_regex = expansion_result.get("desc_regex", raw_title_regex)
    
    queries = []
    
    # 1. タイトル・名称 (rdfs:label / schema:name) 検索
    title_chunks = chunk_regex_str(raw_title_regex, chunk_size=12)
    for c_idx, t_pattern in enumerate(title_chunks):
        p_name = f"1-{c_idx+1}. タイトル・名称 網羅検索 (Part {c_idx+1})" if len(title_chunks) > 1 else "1. タイトル・名称 (label / name) 網羅検索"
        def make_q_title(pat):
            def q_title(lim, offset=0):
                return f"""
                PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
                PREFIX schema: <http://schema.org/>
                
                SELECT DISTINCT ?s WHERE {{
                  {{
                    ?s rdfs:label ?title .
                    FILTER (REGEX(?title, "{pat}", "i"))
                  }} UNION {{
                    ?s schema:name ?title .
                    FILTER (REGEX(?title, "{pat}", "i"))
                  }}
                }}
                OFFSET {offset}
                LIMIT {lim}
                """
            return q_title
        queries.append((p_name, make_q_title(t_pattern)))

    # 2-A. 主題エンティティ (schema:about) 網羅検索 (超高速インデックス仕様: 0.39秒)
    for c_idx, t_pattern in enumerate(title_chunks):
        p_name = f"2A-{c_idx+1}. 主題エンティティ (schema:about) 網羅検索 (Part {c_idx+1})" if len(title_chunks) > 1 else "2A. 主題エンティティ (schema:about) 網羅検索"
        def make_q_about(pat):
            def q_about(lim, offset=0):
                return f"""
                PREFIX schema: <http://schema.org/>
                PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
                
                SELECT DISTINCT ?s WHERE {{
                  ?s schema:about ?about .
                  ?about (rdfs:label|schema:name) ?aboutLabel .
                  FILTER (REGEX(?aboutLabel, "{pat}", "i"))
                }}
                OFFSET {offset}
                LIMIT {lim}
                """
            return q_about
        queries.append((p_name, make_q_about(t_pattern)))

    # 2-B. 主題・件名・キーワード (schema:keywords / dct:subject) 検索
    for c_idx, t_pattern in enumerate(title_chunks):
        p_name = f"2B-{c_idx+1}. キーワード・件名 (keywords / subject) 網羅検索 (Part {c_idx+1})" if len(title_chunks) > 1 else "2B. キーワード・件名 (keywords / subject) 網羅検索"
        def make_q_subject(pat):
            def q_subject(lim, offset=0):
                return f"""
                PREFIX schema: <http://schema.org/>
                PREFIX dct: <http://purl.org/dc/terms/>
                
                SELECT DISTINCT ?s WHERE {{
                  {{
                    ?s schema:keywords ?kw .
                    FILTER (REGEX(STR(?kw), "{pat}", "i"))
                  }} UNION {{
                    ?s dct:subject ?subj .
                    FILTER (REGEX(STR(?subj), "{pat}", "i"))
                  }}
                }}
                OFFSET {offset}
                LIMIT {lim}
                """
            return q_subject
        queries.append((p_name, make_q_subject(t_pattern)))

    # 3. 説明文・内容記述 (schema:description) 検索
    # 長文テキスト属性に対する重い全件走査(504)を防止するため、2文字以上の具体的キーワードに絞込み、最大5パートに最適化
    desc_kws = [w for w in re.split(r"\|", raw_desc_regex) if len(w.strip()) >= 2]
    safe_desc_regex = "|".join(desc_kws) if desc_kws else raw_desc_regex
    desc_chunks = chunk_regex_str(safe_desc_regex, chunk_size=8)[:5]

    for c_idx, d_pattern in enumerate(desc_chunks):
        p_name = f"3-{c_idx+1}. 説明文 網羅検索 (Part {c_idx+1})" if len(desc_chunks) > 1 else "3. 説明文 (description) 網羅検索"
        def make_q_desc(pat):
            def q_desc(lim, offset=0):
                return f"""
                PREFIX schema: <http://schema.org/>
                PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
                
                SELECT DISTINCT ?s WHERE {{
                  ?s rdfs:label ?label .
                  ?s schema:description ?desc .
                  FILTER (REGEX(?desc, "{pat}", "i"))
                }}
                OFFSET {offset}
                LIMIT {lim}
                """
            return q_desc
        queries.append((p_name, make_q_desc(d_pattern)))

    # 4. NDC 二次区分分類 (schema:genre) 網羅検索
    ndc_codes = expansion_result.get("ndc_codes", [])
    if isinstance(ndc_codes, str):
        ndc_codes = [c.strip() for c in re.split(r"[\n,・/／]+", ndc_codes) if c.strip()]

    if ndc_codes:
        filter_exprs = []
        for code in ndc_codes:
            c = str(code).strip()
            if not c:
                continue
            if c.startswith("http"):
                filter_exprs.append(f'STRSTARTS(STR(?genre), "{c}")')
            else:
                filter_exprs.append(f'(STRSTARTS(STR(?genre), "http://jla.or.jp/data/ndc#{c}") || STRSTARTS(STR(?genre), "{c}"))')
        
        if filter_exprs:
            filter_str = " ||\n              ".join(filter_exprs)
            def q_ndc(lim, offset=0):
                return f"""
                PREFIX schema: <http://schema.org/>
                
                SELECT DISTINCT ?s WHERE {{
                  ?s schema:genre ?genre .
                  FILTER (
                    {filter_str}
                  )
                }}
                OFFSET {offset}
                LIMIT {lim}
                """
            queries.append(("4. NDC分類 (schema:genre) 網羅検索", q_ndc))

    return queries

