import os
import json
import sys

# テストターゲット
RULES_FILE = "./02_rule_based_filtering/about_rules.json"

def load_rules():
    with open(RULES_FILE, 'r', encoding='utf-8') as f:
        return json.load(f)

def save_rules_all(noise_set, strong_set):
    rules = {
        "NOISE_PATTERNS": sorted(list(noise_set)),
        "STRONG_KEYWORDS": sorted(list(strong_set))
    }
    with open(RULES_FILE, 'w', encoding='utf-8') as f:
        json.dump(rules, f, ensure_ascii=False, indent=2)

def test_uncheck_save():
    # 1. 元のルールをバックアップ
    original_rules = load_rules()
    orig_noise = set(original_rules.get("NOISE_PATTERNS", []))
    orig_strong = set(original_rules.get("STRONG_KEYWORDS", []))
    
    # テスト対象の単語
    target_word = "https://jpsearch.go.jp/term/keyword/一般図書--語学"
    
    print(f"--- テスト開始 ---")
    print(f"元のブラックリスト数: {len(orig_noise)}")
    
    if target_word not in orig_noise:
        print(f"エラー: テスト用単語 '{target_word}' が元のブラックリストに存在しません。")
        sys.exit(1)
        
    print(f"テスト用単語 '{target_word}' がブラックリストに存在することを確認しました。")
    
    # 2. チェックを外した（セットから削除した）状態をシミュレート
    edited_noise = orig_noise.copy()
    edited_noise.remove(target_word)
    edited_strong = orig_strong.copy()
    
    print(f"チェックを外した後のブラックリスト数（メモリ上）: {len(edited_noise)}")
    
    # 3. 保存
    save_rules_all(edited_noise, edited_strong)
    print("データを JSON に保存しました。")
    
    # 4. 再ロードして検証
    reloaded_rules = load_rules()
    reloaded_noise = set(reloaded_rules.get("NOISE_PATTERNS", []))
    
    print(f"再ロード後のブラックリスト数: {len(reloaded_noise)}")
    
    if target_word in reloaded_noise:
        print("❌ テスト失敗: 削除した単語が JSON に残っています！")
        success = False
    else:
        print("✅ テスト成功: 削除した単語が JSON から正しく消えています！")
        success = True
        
    # 5. 元の状態に復元
    save_rules_all(orig_noise, orig_strong)
    print("元のルールファイルに復元しました。")
    
    if not success:
        sys.exit(1)

if __name__ == "__main__":
    test_uncheck_save()
