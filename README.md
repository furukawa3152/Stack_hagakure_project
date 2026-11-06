# はがくれ君

M5Stack Core2 の画面に置く、ちょんまげのキャラクターです。人の会話を聞き、名前を呼ばれたら返すところまでを目指します。今あるのは、その前段のコンピュータ側だけです。

実機への書き込み、Gemini、Grok Bot 接続はまだです。画面のプレビューと、音声フレームのエコーは、Core2 がなくても確認できます。

## 準備で置いたもの

- `server/` — WebSocket Gateway。PCM を返し、発言してよいかを判断する。
- `simulator/preview.html` — 原画の表情プレビュー。
- `simulator/mock_device.py` — ダミー PCM を送る端末。
- `config/config.example.yaml` — 呼び名と段階Aのパラメータ。
- `docs/decisions.md` — Groki Bot を調べたうえでの採用理由。

原画は `assets/reference/chonmage_character_reference.jpeg` です。

## Windows（Git Bash）

```bash
python -m venv server/.venv
source server/.venv/Scripts/activate
pip install -e "./server[dev]"
pytest -q
python -m hagakure --check
python -m hagakure
```

`pytest` は `server/` で実行しても、リポジトリのルートで実行しても構いません。ルートで実行する場合は、パッケージを editable インストールしたあとの `pytest` を使ってください。設定ファイルは `server/pyproject.toml` の `testpaths` を見ます。ルートからなら次でも動きます。

```bash
python -m pytest server/tests -q
```

## プレビュー

Gateway を起動したまま、ブラウザで <http://127.0.0.1:8776/simulator/preview.html> を開きます。

1. 「接続する」を押す。表示は MIC OFF、CLOUD INACTIVE。
2. 「マイク ON」を押す。
3. 入力が「はがくれ君、どう思う？」のまま「判断させる」を押す。返答する、と出ます。
4. 文を「今度の勉強会どうしよう」に変えてもう一度押す。黙る、と出ます。
5. 表情のボタンで、考えている、話している、を切り替える。

別の端末からエコーを見るときは、Gateway を起動したまま次を実行します。

```bash
python simulator/mock_device.py
```

Mac でのパスの違いは [docs/setup-mac.md](docs/setup-mac.md) にあります。

## 秘密

`.env.example` を `.env` にコピーします。API キーは空のままで、この段階では使われません。LAN に待受を広げるときは `HAGAKURE_DEVICE_TOKEN` を入れてください。空トークンのまま `0.0.0.0` では接続を受けません。

## まだやらないこと

CoreS3 用の Groki Bot ファームウェアは Core2 に書き込まないでください。手順が無いことは [docs/flash-core2.md](docs/flash-core2.md) に、未確認の範囲は [docs/limitations.md](docs/limitations.md) に書いてあります。
