# アーキテクチャ

2026-11-06 時点。実機とクラウドは未接続。

## このリポジトリが今やること

```text
プレビュー (ブラウザ) ──WebSocket──▶ Gateway (Python)
モック端末 (PCM)     ──WebSocket──▶ Gateway
Gateway は PCM をエコーし、発言してよいかを理由コードで返す
Gemini Live と Grok Bot へは矢印がない
```

Core2 が来てからは、同じ WebSocket に実機をつなぐ。クラウドとの会話はその先のアダプターに足す。

```text
人 ──マイク/スピーカー── Core2 ──Wi-Fi── Gateway ── Gemini Live
                                              └── 必要なときだけ Grok Bot
```

首振り、カメラ、外部ディスプレイは作らない。

## Groki Bot で確認したこと

取得コミット: `699a370493e30b196cc7f73f712322cc55c28ec2`。

Gateway は `gateway/` にあり、MIT。ロボットとは XiaoZhi の WebSocket（既定 `0.0.0.0:8765`）で話す。

- `hello` の音声形式は Opus、16 kHz、モノラル、60 ms。下りは 24 kHz を明示する（`gateway/stackchan_mcp/protocol.py`）。
- バイナリフレームは Opus パケットそのもの（`esp32_client.py`）。PCM の独自ヘッダではない。
- 認証は `Authorization: Bearer` と `STACKCHAN_TOKEN`。
- 通常の声は Gemini Live。モデル名の既定は README 上 `gemini-3.8-live`。Grok のログイン音声は macOS の別経路（`127.0.0.1:18771`）。
- Gemini から Grok Bot へ渡すツール名は `ask_grokbot`。有効条件は `STACKCHAN_TOOL_BOT`。転送役は `stackchan-gbot-proxy` で、`127.0.0.1:18770` にだけ束縛し、`gbot --json send` とスレッドのポーリングを行う（`docs/architecture.md` の path 3）。
- 対応ハードウェアの表に Core2 はない。CoreS3 のオーディオは ES8388 系で、Core2 の PDM マイク（SPM1423）とは違う。
- ファームウェア同梱の Emotion Ball 目データは非商用。Gateway 以外の本体ライセンスは BSL-1.0。

この Gateway 自体は、今回起動も試験もしていない。API キーと macOS 用の音声ライブラリが要るため。

## はがくれ君側の境界

| 部品 | 場所 | 今の中身 |
|---|---|---|
| DeviceTransport | `server/src/hagakure/transport/` | `/device` の WebSocket。JSON と PCM を分ける |
| ConversationPolicy | `server/src/hagakure/conversation/policy.py` | 段階Aの判断。Gemini の往復でも、呼び名が無い音声は返さない。本文は保存しない |
| 状態 | `server/src/hagakure/conversation/state.py` | 仕様の 9 状態 |
| AvatarController | `server/src/hagakure/avatar/controller.py` | 状態名と、振幅から口の開き |
| VoiceBackend | `server/src/hagakure/adapters/voice.py` | 同じ接続でセッションを使い回す。音声チャンクは届き次第 16 kHz へ詰める |
| TaskAgent | `server/src/hagakure/adapters/task_agent.py` | Grok Bot は拒否 |
| プレビュー | `simulator/preview.html` | 顔パーツを重ね、瞬きと口の開閉 |
| ファームウェア | `firmware/core2/README.md` | 未着手 |

判断の順序は、マイク OFF、自分の発話中、人の発話、空の書き起こし、呼び名、自発発言の条件、の順。自発発言は設定で切ってある。

詳細なフレームは [protocol.md](protocol.md)、採否の理由は [decisions.md](decisions.md)。
