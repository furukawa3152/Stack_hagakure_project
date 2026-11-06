# テスト計画

仕様書の T01 から T14 は、実機とクラウドがそろうまで合格にしない。

## 今実行するもの

| 確認 | 方法 |
|---|---|
| 20 ms フレームが 640 バイト | `server/tests/test_protocol.py` |
| 状態遷移が仕様の並びに沿う | `server/tests/test_state.py` |
| 呼び名だけ返答し、それ以外は黙る | `server/tests/test_policy.py` |
| マイク OFF で音声を捨てる | `server/tests/test_session.py` |
| 認証失敗とループバック制限 | 同上 |
| 書き起こし本文を返答に含めない | 同上 |
| WebSocket で PCM が往復する | `server/tests/test_gateway.py` |
| プレビューで原画、MIC 表示、接続、判断が見える | ブラウザで `simulator/preview.html` |

## 実機待ち

| ID | 内容 |
|---|---|
| T01 | USB 書き込みと再起動 |
| T02 | 実機の画面とタッチ |
| T03 | SoftAP での Wi-Fi 設定 |
| T04 | Core2 から Mac への連続音声 |
| T05 | Mac から Core2 スピーカー |
| T06 | 指名に対する日本語音声 |
| T07 | 30 分の再接続 |
| T08 | 自発発言 |
| T09 | 人の発話中に割り込まないこと（実音） |
| T10 | Grok Bot への依頼と復帰 |
| T11 | 複数 Mac |
| T12 | 実機の MIC OFF で送信が止まること。サーバ側の破棄は単体テスト済み |
| T13 | Wi-Fi 切断と API 失敗からの復帰 |
| T14 | セッションごとの使用量 |

計測値（遅延、欠落、誤起動）は、実験するまで空欄にする。
