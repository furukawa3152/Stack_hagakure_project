# デバイスプロトコル v1

Groki Bot / XiaoZhi の互換プロトコルではない。

## 接続

- `ws://127.0.0.1:8775/device`
- 最初のメッセージは JSON の `hello`。10 秒を超えると切る。
- トークンは `hello.token`、または `Authorization: Bearer ...`。
- トークン未設定の Gateway は、待受ホストがループバックのときだけ受ける。
- `/device` 以外のパスは閉じる。

```json
{
  "type": "hello",
  "protocol_version": 1,
  "device_id": "core2-001",
  "token": "共有秘密",
  "audio_in": {"rate": 16000, "channels": 1, "format": "pcm_s16le"}
}
```

```json
{
  "type": "hello_ack",
  "protocol_version": 1,
  "session_id": "サーバが発行",
  "gateway": "hagakure",
  "mic_enabled": false,
  "phase": "muted",
  "cloud_active": false,
  "audio_out": {"rate": 16000, "channels": 1, "format": "pcm_s16le"}
}
```

この版の下りも 16 kHz である。24 kHz 再生は実機のドライバを見てから決める。`cloud_active` はクラウドへつなぐまで false。

## 制御 JSON

`ping`、`pong`、`mute`、`mute_ack`、`device_state`、`device_state_ack`、`touch`、`touch_ack`、`expression`、`transcript`、`policy_decision`、`interrupt`、`interrupt_ack`、`error`。

`mute` は `{"type":"mute","mic_enabled":true}`。false のあいだ上り音声は捨てる。

`transcript` は試験用。Gateway は本文をログに残さず、`policy_decision` で `action` と `reason` だけ返す。音声の返答は生成しない。

`interrupt` は発話世代 `generation` を進める。話している状態のときだけ `interrupted` へ移る。

## 音声バイナリ

リトルエンディアン 20 バイトのあとが PCM。

| 位置 | 型 | 意味 |
|---|---|---|
| 0 | 2 バイト | `HG` |
| 2 | u8 | バージョン `1` |
| 3 | u8 | `1` マイク上り、`2` スピーカー下り |
| 4 | u32 | シーケンス |
| 8 | u32 | タイムスタンプ（ミリ秒） |
| 12 | u16 | サンプルレート |
| 14 | u16 | ペイロード長 |
| 16 | u32 | 発話世代 |

初期フレームは 20 ms、640 バイト、16 kHz、モノラル、16 bit リトルエンディアン。音声の再送はしない。制御 JSON は再接続時に `hello` からやり直す。

マイク ON のあいだ、Gateway は上りを種別 `2` の下りとして返す。これは疎通確認用のエコーで、AI の声ではない。エコーの世代は、遅れて届いた音声を捨てるための番号で、上りフレームに入っていた世代は使わない。
