# Enhance Music Scores Findability Project

このプロジェクトは、ジャパンサーチの「古書・古文書」カテゴリに埋もれている楽譜データを高精度に抽出・クレンジングし、メタデータ（楽器情報など）を付与してリッチ化するための研究用リポジトリです。

## プロジェクト概要
「譜」という言葉の多義性（家譜、年譜、画譜などのノイズ）を排除し、本物の「楽譜」のみを系統的に抽出します。タイムアウトが発生しやすい複雑なSPARQLクエリを避け、ローカル環境（Python + LLM + 人間によるWebアプリ査読）でフィルタリングを行うハイブリッド方式を採用しています。

## 整理後のフォルダ構成
```
.
├── README.md                   # 本ドキュメント
├── metadata_field_counts.csv   # 取得したメタデータのフィールドカバレッジ統計
├── field_coverage_bnodes.png   # フィールドカバレッジの可視化グラフ
├── heatmap_with_bnodes.png    # フィールドカバレッジのヒートマップ
├── extract_scores.py           # 楽譜レコードから「〇〇譜」を抽出・集計するスクリプト
│
├── 01_data_collection/         # 第1段階：データ収集
│   ├── URIListMaker.py         # SPARQLからURI一覧抽出 (約1.8万件)
│   └── BuildMetadata.py        # 詳細メタデータ構築 (JSONL化)
│
├── 02_rule_based_filtering/    # 第2段階：ルールベースのノイズ除去
│   ├── about抽出.py            # Aboutキーワードの抽出
│   ├── app_about.py            # Aboutキーワード仕分け Streamlitアプリ
│   ├── about_filter.py         # Aboutフィルタの適用 (ノイズ除外)
│   └── app.py                  # 末尾語彙仕分け Streamlitアプリ
│
├── 03_hybrid_classification/   # 第3段階：スマート判定 ＆ 査読
│   ├── keyword_sorter_dual.py  # スマートN-gram仕分けアプリ
│   ├── split_data_by_lists.py  # OK/NG/グレーの3分割処理
│   ├── lmstudio_filter.py      # ローカルLLM判定 (グレーゾーン対象)
│   ├── result_viewer.py        # LLM結果の査読・修正アプリ
│   └── create_sample_for_review.py # サンプリングレビュー用
│
├── data/                       # 最終成果物データのみを格納
│   ├── classical_scores_cleaned.jsonl # 最終クレンジング済み楽譜データ（6,983件）
│   ├── classical_scores_cleaned.csv   # 分析用にCSV化したデータ
│   └── vocab_ranking_scores.csv       # 楽譜から抽出した「〇〇譜」語彙ランキング
│
└── archive/                    # アーカイブ（中間ファイル・旧バージョン）
    ├── data/                   # 途中段階の中間データや除外ログ
    ├── fragments/              # 途中段階のスクリプトや旧バージョン
    └── 作業中に発生したファイル/   # その他バックアップ
```

## パイプラインの再現手順
1. **URIの取得**: `01_data_collection/URIListMaker.py` で対象URIを抽出。
2. **詳細メタデータの取得**: `01_data_collection/BuildMetadata.py` でブランクノードを含めたローカルグラフJSONLを構築。
3. **Aboutフィルタ**: `02_rule_based_filtering/about抽出.py` 経由で分類キーを抽出し、`02_rule_based_filtering/app_about.py` でNGキーワードを設定。`02_rule_based_filtering/about_filter.py` で適用。
4. **末尾（接尾辞）フィルタ**: `02_rule_based_filtering/app.py` にて末尾が「譜」となる不要語（人参譜など）を仕分け、除外。
5. **N-gram ＆ LLMハイブリッド査読**: `03_hybrid_classification/keyword_sorter_dual.py` で構築したOK/NGワードに基づき、`03_hybrid_classification/split_data_by_lists.py` で3分割。グレーゾーンを `03_hybrid_classification/lmstudio_filter.py` でLLM判定し、`03_hybrid_classification/result_viewer.py` で査読して確定。
