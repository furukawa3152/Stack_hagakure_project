# 決定記録

調査対象は Groki Bot `main` の `699a370493e30b196cc7f73f712322cc55c28ec2`（2026-10-31、"Fix: pass explicit proxy config to the voice bridge LaunchAgent"）です。ローカルの取得先は `.research/groki-bot` で、このリポジトリの成果物には含めません。

## D001 デバイス通信は独自 WebSocket にする

2026-11-06。Core2 向けの端末プロトコルは、Groki Bot Gateway の XiaoZhi 互換サーバーをそのまま使わない。

| 観点 | XiaoZhi Gateway を再利用 | 独自 WebSocket |
|---|---|---|
| 基板 | 公開ドキュメントの対応は CoreS3、AtomS3R、AtomS3、StopWatch。Core2 はない | Core2 向けに別ファームウェアを書く |
| 音声 | Opus、上り 16 kHz、下り 24 kHz、60 ms。バイナリ 1 フレームが Opus 1 パケット | 仕様の初期案どおり PCM 16 bit、16 kHz、20 ms（640 バイト） |
| 会話 | 「Hi Grok」のウェイクワードのあとクラウドへ送る | 段階Aは「はがくれ君」などと呼ばれたときだけ返す |
| 画面 | Groki の表情。目のデータには非商用の Emotion Ball が含まれる | ユーザー提供の原画を使う |
| 範囲外の機能 | サーボ追視、LED、カメラ、MCP が中心に絡む | 音声、顔、タッチ、Wi-Fi に限る |
| Grok Bot | `ask_grokbot` と `127.0.0.1:18770` の転送は実在する | 同じ役割を Phase 5 のアダプターに隔離する。今は呼ばない |
| ライセンス | Gateway は MIT。ファームウェア本体は BSL-1.0 で、第三者分を含む | 今回はコードをコピーしない |

採用理由: CoreS3 用ファームを Core2 に書けない、という制約が先に立つ。Gateway を活かすには Core2 上へ Opus の XiaoZhi クライアントを新規に作る必要があり、その時点で独自実装と工数が重なる。会話方針も画面も違う。保守では、上流のサーボや表情の変更を Core2 側が追わなくてよい。

再利用するのは動きの知識だけにする。

- 接続時の `hello`、トークン、デバイス ID。
- Gemini 側の通常会話と、必要なときだけ Grok Bot へ渡す分離。
- Grok 側は Mac ローカルの `gbot` で、トークンを Gateway が持たない形。

`gateway/LICENSE` は、サーボ SDK が GPL-3.0 だと書いている。このコミットのツリーには、そこに書かれた `firmware/main/boards/stackchan` の SCServo ファイルはなかった。サーボ処理は `components/scs_servo` にある。いずれにせよファームウェアはコピーしない。

Emotion Ball の目データは非商用ライセンスなので使わない。

Gateway の MIT コードを将来部分的に移植する場合は、著作権表示を残す。

## D002 キャラクター名ははがくれ君

呼び名は「はがくれ君」「はがくれ」「ちょんまげ君」。仕様書の例にある「ちょんまげ君」は別名として残す。髪型の話題だけで反応しないよう、単体の「ちょんまげ」は呼び名にしない。

見た目は `assets/reference/chonmage_character_reference.jpeg` の原画に合わせる。パーツを想像で描き直さない。原画の再配布条件は未確認。

## D003 待受は 127.0.0.1:8775

Groki Bot Gateway の 8765 と同時に起動できるように、既定ポートは 8775 にする。プレビューは 8776。

トークンが空のときは `127.0.0.1` / `localhost` / `::1` だけを許す。`0.0.0.0` のまま空トークンでは接続を拒む。LAN へ出すときは `HAGAKURE_DEVICE_TOKEN` を必ず入れる。

## D004 起動時はマイク OFF、音声は保存しない

`hello_ack` の時点で `mic_enabled` は false、状態は `muted`。マイク OFF のあいだ、上りの PCM は捨て、エコーもしない。

`store_raw_audio` が true でも、この版はファイルを作らない。

## D005 自発発言は段階Aのため既定で切る

仕様書の仮パラメータ（閾値 0.85、無音 2 秒、クールダウン 60 秒、5 分に 1 回）は設定に残す。`proactive_enabled` の既定は false。名前を呼ばれたときだけ `speak` / `addressed` になる。

`barge_in_enabled` を true にしても、人の発話中は返さない。エコーキャンセルは未評価。

## D006 開発機は Windows、想定の常駐先は Mac

この準備は Windows 上で行った。Gateway は CPython で動き、Mac mini へ移せる。`launchd`、mDNS、Grok Bot アプリの疎通は Mac が来てからで、未実施とする。

## D007 Gemini と Grok Bot は未接続

アダプターのクラスはある。`GeminiLiveBackend.connect` と `GrokBotTaskAgent.submit_task` は `NotImplementedError` を出す。キーがあっても API を呼ばない。

Phase 1 の音声は、マイク ON のあいだ PCM をそのまま返すエコーだけである。これは会話の返答ではない。

## D008 実機のリビジョンは未確認

Core2 と Core2 v1.1 のどちらを使うかは記録がない。オーディオドライバは選んでいない。ファームウェアのソースは置いていない。
