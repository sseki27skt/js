import sys
import os
import json

# Pythonパスに追加して02_rule_based_filtering内のモジュールを読み込めるようにする
sys.path.append(os.path.abspath('02_rule_based_filtering'))

from about_filter import NOISE_PATTERNS, STRONG_KEYWORDS

rules = {
    "NOISE_PATTERNS": NOISE_PATTERNS,
    "STRONG_KEYWORDS": STRONG_KEYWORDS
}

output_path = '02_rule_based_filtering/about_rules.json'
with open(output_path, 'w', encoding='utf-8') as f:
    json.dump(rules, f, ensure_ascii=False, indent=2)

print(f"Successfully exported hardcoded lists to {output_path}")
