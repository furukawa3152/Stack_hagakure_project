# はがくれ君 Core2 運用メモ

更新: 2026-11-08

## 現在の構成

- 基板: M5Stack Core2。CoreS3 用の Groki Bot ファームウェアは使わない。
- Mac の Gateway が Gemini Live と通信する。基板は同じ LAN の Gateway `192.168.0.11:8775` に接続する。
- `cb` は呼び名なしで会話、`ag` は呼びかけ判定、`gb` は未実装。
- Gemini の話者は `Puck`。会話テキストは `data/conversations/` にセッションごとに保存し、Git には含めない。音声そのものは保存しない。
- Core2 の返答音声バッファは 48 秒分。cb の発話開始は平均振幅 500 以上が 5 フレーム連続、送信には強いフレームが 8 枚以上必要。

## 確認済みと残る確認

- Gateway のテスト 57 件が成功。Core2 の書き込みとハッシュ検証が成功。実機で Wi-Fi、Gateway 接続、複数ターンの再生、会話ファイルの作成を確認。
- 短い返答では音声破棄数 `0`。48 秒に近い返答と、さまざまな環境雑音や小声での判定は未確認。
- テキストは Gemini が書き起こしを返した分だけ保存される。届かないターンは欠落を明記する。

## 別の Mac で使う

1. GitHub の最新コミットを clone する。移行時に未コミットの変更があれば別途移す。
2. Git 管理外の `.env` と `firmware/core2/wifi_link/secrets.h` を安全に移す。会話記録が必要なら `data/conversations/` も別途移す。
3. Python 3.11 以上で仮想環境を作り、`python -m pip install -e './server[dev]'`、`python -m pytest server/tests -q`、`python -m hagakure` を実行する。
4. 新しい Mac の IP が `192.168.0.11` と違う場合は `secrets.h` の `HAGAKURE_GATEWAY_HOST` を変更し、Core2 専用 FQBN `m5stack:esp32:m5stack_core2` で書き込む。

詳細: `docs/setup-mac.md`、`docs/decisions.md`、`docs/limitations.md`。
