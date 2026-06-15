import subprocess
import json
import pandas as pd
import csv

# Gitのコミット履歴から元の fragments/about_filter.py のコードを直接ロード
git_cmd = ["git", "show", "HEAD:fragments/about_filter.py"]
try:
    code_text = subprocess.check_output(git_cmd).decode('utf-8')
    
    # 実行用のローカル変数を設定
    local_vars = {
        'pd': pd,
        'csv': csv
    }
    
    # コードを実行して定義を抽出
    exec(code_text, {}, local_vars)
    
    rules = {
        "NOISE_PATTERNS": local_vars.get("NOISE_PATTERNS", []),
        "STRONG_KEYWORDS": local_vars.get("STRONG_KEYWORDS", [])
    }
    
    output_path = '02_rule_based_filtering/about_rules.json'
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(rules, f, ensure_ascii=False, indent=2)
        
    print(f"Successfully restored rules.json: {len(rules['NOISE_PATTERNS'])} noise, {len(rules['STRONG_KEYWORDS'])} strong patterns.")
except Exception as e:
    print(f"Failed to restore rules.json: {e}")
