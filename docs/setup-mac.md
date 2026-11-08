# 別の Mac で動かす

Core2 と Mac を同じ LAN に接続する。現在の Core2 は Gateway の接続先 `192.168.0.11:8775` をファームウェアに保持している。別の Mac の LAN アドレスが異なる場合は、`firmware/core2/wifi_link/secrets.h` の `HAGAKURE_GATEWAY_HOST` を変更して Core2 用スケッチを書き直す。CoreS3 用ファームウェアは使わない。

## 1. プロジェクトを移す

GitHub の最新コミットを clone する。移行時に未コミットの変更があれば、それは clone に含まれないため別途移す。`server/.venv` は移さず、新しい Mac で作り直す。

秘密情報は `.env` と `firmware/core2/wifi_link/secrets.h` にある。これらは Git 管理外なので、安全な方法で別途移す。`.env` の `HAGAKURE_DEVICE_TOKEN` は Core2 に書き込んだトークンと一致させる。`GEMINI_API_KEY` も新しい Mac に設定する。会話記録が必要なら、Git 管理外の `data/conversations/` も別途移す。

## 2. Gateway を起動する

Python 3.11 以上が必要。新しい Mac で以下を実行する。

```bash
cd /path/to/Stack_hagakure_project
python3 -m venv server/.venv
source server/.venv/bin/activate
python -m pip install -e './server[dev]'
python -m pytest server/tests -q
python -m hagakure --check
python -m hagakure
```

`.env` は次の値を確認する。キーとトークンの値を画面やログに貼らない。

```text
HAGAKURE_HOST=0.0.0.0
HAGAKURE_PORT=8775
HAGAKURE_VOICE=gemini
HAGAKURE_SAVE_TRANSCRIPTS=1
HAGAKURE_DEVICE_TOKEN=（Core2 と同じ値）
GEMINI_API_KEY=（新しい Mac のキー）
```

macOS のファイアウォールで Python の着信を許可し、Core2 から TCP 8775 に到達できるようにする。プレビューは新しい Mac のブラウザで `http://127.0.0.1:8776/simulator/preview.html` を開く。会話記録は `data/conversations/` に保存される。古い Mac の Gateway は停止してから新しい Mac で運用する。

## 3. Core2 の接続先を変える場合

新しい Mac の LAN アドレスを確認し、`firmware/core2/wifi_link/secrets.h` の `HAGAKURE_GATEWAY_HOST` に設定する。Wi-Fi とトークンも確認する。M5Stack の Arduino コアと M5Unified など、スケッチの依存ライブラリを新しい Mac に入れてから、Core2 専用 FQBN でビルドと書き込みを行う。

```bash
arduino-cli compile --fqbn m5stack:esp32:m5stack_core2 firmware/core2/wifi_link
arduino-cli board list
arduino-cli upload --fqbn m5stack:esp32:m5stack_core2 --port /dev/cu.usbserial-XXXX firmware/core2/wifi_link
```

`/dev/cu.usbserial-XXXX` は `arduino-cli board list` に出た Core2 のポートに置き換える。現在の Mac の実機では `0225B38F` だったが、新しい Mac でも同じ名前になるとは限らない。書き込み後は Gateway の接続と実際の会話を確認する。
