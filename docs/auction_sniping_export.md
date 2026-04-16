# オークション仕入れ: 指値(スナイプ)予約データ出力 v1

## 目的
オークション形式の候補について、利益率30%を確保できる上限入札額（指値）を算出し、
予約入札用データをCSVで出力する。

> 本機能は「予約用データ出力」を行う。外部サービスへの自動入札実行そのものは、
> 各サービスの利用規約・提供機能の範囲で行うこと。

## 入力
`templates/auction_candidates_template.csv` をベースに、以下列を与える。
- `listing_id`
- `title`
- `url`
- `format` (`auction` / `buy_now`)
- `end_at` (ISO-8601)
- `expected_sell_price_jpy`
- `current_price_jpy`

## 算出ルール
目標利益率 `target_margin_rate = 0.30` を満たす最大入札額を計算する。

- 手数料率: 10%
- 仕入送料: 1,200円
- 販売送料: 750円
- 入札単位: 100円（`--bid-unit` で変更可）

計算式:

`max_bid = floor(expected_sell * (1 - sell_fee_rate - target_margin_rate) - sale_shipping - purchase_shipping)`

実際の出力は入札単位で切り捨て。

## 出力プロファイル
取り込み列名が不明でも使えるように、3種類の出力を用意。

1. `internal`（既定）
   - 技術用の英語列名
2. `jp_basic`
   - 日本語列名（暫定）
3. `aucfan_manual`
   - 手入力しやすい最小列（商品URL、入札金額、分前タイミングなど）

さらに、`--header-map` で列名を自由に差し替え可能。
例: `templates/aucfan_header_map_example.json`

## スクショ前提の運用（オークファン手入力）
提示された画面では「分前」と「入札金額」を手入力するUIのため、
`aucfan_manual` でCSVを出し、上から順に入力する運用を推奨。

## 実行例
### 1) オークファン手入力用CSV
```bash
python tools/generate_aucfan_reservations.py \
  --input templates/auction_candidates_template.csv \
  --output out/aucfan_manual_input.csv \
  --output-profile aucfan_manual \
  --reserve-minutes 6
```

### 2) 日本語の暫定列名で出力
```bash
python tools/generate_aucfan_reservations.py \
  --input templates/auction_candidates_template.csv \
  --output out/aucfan_reservations_jp.csv \
  --output-profile jp_basic
```
