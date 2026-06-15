# -*- coding: utf-8 -*-
import sys
import os

# プロジェクトのルートディレクトリをパスに追加
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from integrated_portal.modules.importer import import_existing_assets, get_import_status

def main():
    print("=== インポート前ステータス ===")
    status = get_import_status()
    for name, s in status.items():
        print(f"File: {name} | 元存在: {s['source_exists']} | 移植先存在: {s['dest_exists']}")
        
    print("\n=== インポート開始（コピー） ===")
    results = import_existing_assets(overwrite=True)
    for r in results:
        print(f"Dest: {r['file']} | 状況: {r['status']} | メッセージ: {r['message']}")
        
    print("\n=== インポート後ステータス ===")
    status = get_import_status()
    all_ok = True
    for name, s in status.items():
        print(f"File: {name} | 元存在: {s['source_exists']} | 移植先存在: {s['dest_exists']}")
        if s['source_exists'] and not s['dest_exists']:
            all_ok = False
            
    # 元ファイルの破損がないかチェック
    print("\n=== 元ファイル存在確認 ===")
    test_sources = [
        "data/target_uris_classical_retry.csv",
        "data/classical_scores_dynamic.jsonl",
        "02_rule_based_filtering/about_rules.json",
        "fragments/ngram/ok_word_list.txt"
    ]
    for src in test_sources:
        if os.path.exists(src):
            size = os.path.getsize(src)
            print(f"Original: {src} -> OK (サイズ: {size} bytes)")
        else:
            print(f"Original: {src} -> ⚠️消失しています！")
            all_ok = False
            
    if all_ok:
        print("\n🎉 テスト成功: インポートは無事に完了し、オリジナルは完全に温存されました。")
    else:
        print("\n⚠️ テスト失敗: ファイルが正しく移行されていないか、消失の恐れがあります。")

if __name__ == "__main__":
    main()
