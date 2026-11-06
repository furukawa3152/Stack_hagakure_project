# 開発ログ

## 2026-11-06 準備

仕様書 `Chonmage_AI_Core2_Development_Spec.md` の最初の作業として、Groki Bot の調査と、実機なしで動く土台を置いた。

### 調査

- clone 先: `.research/groki-bot`（配布物にしない）
- コミット: `699a370493e30b196cc7f73f712322cc55c28ec2`
- Gateway は MIT。端末プロトコルは XiaoZhi、音声は Opus。`ask_grokbot` と `127.0.0.1:18770` の転送はコード上に存在する。
- 対応基板の表に Core2 はない。Emotion Ball の目データは非商用。ファームウェアはコピーしていない。
- Groki Bot の Gateway 自体は起動していない。

採用は独自 WebSocket。理由は [decisions.md](decisions.md)。

### 作ったもの

- Python Gateway。`ws://127.0.0.1:8775/device`。起動時はマイク OFF。マイク ON のあいだだけ PCM をエコーする。
- 発言判断。呼び名があるときだけ「返答してよい」。ないときは黙る。本文はログに残さない。
- 原画プレビュー。`http://127.0.0.1:8776/simulator/preview.html`
- ダミー端末 `simulator/mock_device.py`
- Gemini と Grok Bot のクラスは、呼ぶと未実装だと返す。

### 確認したこと

- `python -m pytest server/tests -q` : 27 件成功。
- `python simulator/mock_device.py` : 640 バイトのエコーが返り、`cloud=False`。
- ブラウザでプレビューを操作した。原画が表示される。未接続のときは黒目の位置が肌色で覆われ、待機にすると元の黒目に戻る。話している、では口の位置の色が変わる。接続後は MIC OFF / CLOUD INACTIVE / マイク停止。マイク ON のあと「はがくれ君、どう思う？」は「返答してよい」、「今度の勉強会どうしよう」は「黙る」。受信ログに書き起こし本文は出なかった。
- この確認は Windows 上。Mac と Core2 では未実施。

### 実機待ち

基板リビジョン、LCD、タッチ、PDM マイク、スピーカー、Wi-Fi、SoftAP、Gemini の日本語音声、Grok Bot の単独疎通。

### 次の作業

1. 手持ちの Core2 が通常版か v1.1 かを型番で確認する。
2. LCD とタッチだけの最小ファームを書き、起動を記録する。
3. 16 kHz の上りと、スピーカー再生を個別に測ってから、この Gateway とつなぐ。
4. そのあとで Gemini Live をアダプターに入れる。Grok Bot はその前に Mac 上で `gbot` が単体で通ることを見る。
