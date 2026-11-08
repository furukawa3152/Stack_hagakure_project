# Core2 への書き込み

2026-11-07。LCD とタッチだけのスケッチ `firmware/core2/lcd_touch` を、入っていた M5Stack Arduino コア 3.3.10（FQBN `m5stack:esp32:m5stack_core2`）でビルドし、`/dev/cu.usbserial-0225B38F` に書いた。書き込み後のハッシュ検証は通った。シリアルでは `board=2 M5StackCore2`、`power=axp192`、`vbat_mV=4133`、`display=320x240`、`ready`、`loop` まで出た。00:49 ごろ、利用者の確認では画面に文字が出ている。00:51 ごろのタッチは `touch x=147 y=159` と `touch x=214 y=123`。そのあと `firmware/core2/audio_check` を書いた。今入っているのはこちらである。スピーカーは 48000 Hz で 440 Hz を2回、マイクは 16000 サンプルを 960 ms。01:06 ごろ、利用者にはその音が聞こえた。そのあと `firmware/core2/wifi_link` を書いた。今入っているのはこちらである。`aterm-fb23d0-g` のチャンネル 11 に入り、`192.168.0.13` から `hello_ack` と `pong` まで確認した。続けて同じスケッチで 16 kHz の 100 フレームを送り、`echo_match=1`、`speaker_play=1` まで確認した。01:45 ごろ、利用者にはその再生が聞こえた。07:30 ごろ、`utterance_end` を足した版を書いた。最初は下り 0 フレーム、`speaker_play=0` だった。20:56 ごろ、同じスケッチで下り 204 フレーム、`speaker_play=1` まで進んだ。パスワードとトークンはリポジトリに置いていない。

ボード設定はコアの既定（Flash 16MB、QIO、80MHz、PSRAM あり）。ROM の起動行は `mode:DIO, clock div:1` のままだった。

Groki Bot の Web フラッシャーや CoreS3 用バイナリは、この基板に使わないでください。
