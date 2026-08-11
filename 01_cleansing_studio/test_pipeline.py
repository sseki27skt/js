# -*- coding: utf-8 -*-
"""
Japan Search メタデータ自動取得パイプライン ＆ 高速LLMサジェストの総合テスト
"""

import os
import sys
import json
import time
import tempfile

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "modules")))

from llm_query_expander import expand_query_with_llm, generate_sparql_queries
from sparql_collector import fetch_uris_with_query_func, build_metadata_for_uris
from rule_filter import suggest_ng_keywords_with_llm, suggest_related_keywords_by_base


def test_fast_llm_suggestions():
    print("\n=== [Test 5] Fast LLM Context Suggestion Test ===")
    dummy_ng_list = [f"ダミー除外語_{i}" for i in range(500)]  # 500件の大規模リスト
    sample_kws = ["歴史", "写真", "絵画", "浄瑠璃", "雅楽", "能楽", "三味線", "地図", "軍記", "書誌"]
    target_kws = ["楽譜", "音楽", "音譜", "能楽"]

    start_time = time.time()
    suggs = suggest_ng_keywords_with_llm(
        current_ng_list=dummy_ng_list,
        sample_keywords=sample_kws,
        target_keywords=target_kws,
        domain_definition="日本の古典籍楽譜"
    )
    elapsed = time.time() - start_time
    print(f"[OK] Fast Suggestion Response Time: {elapsed:.2f} 秒")
    print(f"[OK] Returned Suggestions ({len(suggs)} items): {suggs}")
    assert elapsed < 15.0, "Response took longer than 15 seconds!"

    start_time2 = time.time()
    related_suggs = suggest_related_keywords_by_base("浄瑠璃", mode="ok", sample_keywords=sample_kws)
    elapsed2 = time.time() - start_time2
    print(f"[OK] Contextual Base Suggestion Response Time: {elapsed2:.2f} 秒")
    print(f"[OK] Related OK Suggestions for '浄瑠璃': {related_suggs}")


def test_llm_query_expansion():
    print("=== [Test 1] LLM Query Expansion Test ===")
    theme = "日本の古典籍における楽譜資料"
    res = expand_query_with_llm(theme)
    assert isinstance(res, dict), "Result is not dict"
    assert "theme" in res, "No theme field"
    assert "keywords" in res, "No keywords field"
    print(f"[OK] Theme: {res.get('theme')}")
    print(f"[OK] Keywords: {res.get('keywords')}")
    return res


def test_sparql_query_generation(expansion_res):
    print("\n=== [Test 2] SPARQL Query Generation Test ===")
    queries = generate_sparql_queries(expansion_res, limit=20)
    assert len(queries) > 0, "No queries generated"
    return queries


if __name__ == "__main__":
    print("--------------------------------------------------")
    print("  Japan Search Enhanced Pipeline & Fast Suggest Test")
    print("--------------------------------------------------")
    try:
        test_fast_llm_suggestions()
        exp_res = test_llm_query_expansion()
        queries = test_sparql_query_generation(exp_res)
        print("\n==================================================")
        print(" SUCCESS: All enhanced pipeline tests passed!")
        print("==================================================")
    except Exception as e:
        print(f"\n[FAIL] Test Failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
