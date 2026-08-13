# -*- coding: utf-8 -*-
"""
MetaClean Studio - ファイル操作 ＆ ヘルパーユーティリティ
"""

import json
import os
import tempfile
import urllib.parse


def count_lines(path: str) -> int:
    """指定されたファイルの行数またはJSON要素数を取得"""
    if not os.path.exists(path):
        return 0
    if path.endswith('.json'):
        try:
            with open(path, 'r', encoding='utf-8', errors='ignore') as f:
                data = json.load(f)
                return len(data) if isinstance(data, list) else 0
        except Exception:
            return 0
    else:
        with open(path, 'r', encoding='utf-8', errors='ignore') as f:
            return sum(1 for line in f if line.strip())


def make_google_link(word: str) -> str:
    """Google検索用のマークダウンリンク文字列を生成"""
    query = urllib.parse.quote(f"{word} とは")
    url = f"https://www.google.com/search?q={query}"
    return f"[🔍]({url})"


def safe_save_json(data, target_path: str) -> bool:
    """
    データ構造（dict/list等）を一時ファイルに書き出してからアトミックにリネーム保存。
    書き込み途中の破損を防ぐ。
    """
    try:
        dir_name = os.path.dirname(target_path)
        if dir_name:
            os.makedirs(dir_name, exist_ok=True)
        
        temp_fd, temp_path = tempfile.mkstemp(dir=dir_name, suffix='.tmp')
        with os.fdopen(temp_fd, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        
        os.replace(temp_path, target_path)
        return True
    except Exception as e:
        if 'temp_path' in locals() and os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except Exception:
                pass
        raise e
