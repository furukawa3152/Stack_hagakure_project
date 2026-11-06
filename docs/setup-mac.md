# Mac での起動

常駐の想定は、Core2 と同じ LAN にある Mac です。この準備作業の実行確認は Windows で行っています。Mac 上ではまだ起動していません。

```bash
cd /path/to/Stack_hagakure_project
python3 -m venv server/.venv
source server/.venv/bin/activate
pip install -e "./server[dev]"
pytest -q
python -m hagakure --check
python -m hagakure
```

ブラウザで <http://127.0.0.1:8776/simulator/preview.html> を開きます。

LAN の Core2 から繋ぐときは、`.env` にトークンを入れ、待受ホストを変えます。トークンなしで `0.0.0.0` にはしません。

```text
HAGAKURE_HOST=0.0.0.0
HAGAKURE_DEVICE_TOKEN=openssl rand -hex 16 の結果
```

`launchd` への登録は、エコー以上の動作が固まってからにします。Grok Bot アプリと `gbot` の確認も、その Mac にログインがある状態で別に行います。
