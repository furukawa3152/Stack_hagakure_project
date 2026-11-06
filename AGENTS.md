# 実装エージェントへの指示

キャラクター名ははがくれ君。基板は M5Stack Core2。CoreS3 用の Groki Bot ファームウェアを書き込まない。

1. 調査、最小の動作、確認の記録、そのあと機能を足す。未確認のものを対応済みと書かない。
2. 首振り、サーボ、カメラ、追視、HDMI は対象外。
3. 仮定は `docs/decisions.md` に足す。秘密は `.env` に置き、例は `.env.example` だけを更新する。
4. 実機がなくても、Gateway とプレビューのテストを止めない。
5. Gemini と Grok Bot はアダプターの外で結合しない。未実装のメソッドを、成功した接続に見せない。
6. 音声の本文と API キーをログやテストの期待値に残さない。
7. 原画 `assets/reference/chonmage_character_reference.jpeg` を別の顔に描き換えない。
