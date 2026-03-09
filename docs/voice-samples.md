# ボイスサンプル比較

Gemini 2.5 Flash TTSの女性ボイスを比較するページです。
各ボイスについてノーマル・高め（x1.15）・低め（x0.85）の3パターンを用意しています。

**サンプルテキスト:** 「こんにちは！あかりです。今日も楽しく配信していきましょう！よろしくお願いします。」

---

## Aoede

| パターン | 再生 |
|---------|------|
| ノーマル | <audio controls src="assets/voice-samples/aoede_normal.wav"></audio> |
| 高め (x1.15) | <audio controls src="assets/voice-samples/aoede_high.wav"></audio> |
| 低め (x0.85) | <audio controls src="assets/voice-samples/aoede_low.wav"></audio> |

---

## Kore

| パターン | 再生 |
|---------|------|
| ノーマル | <audio controls src="assets/voice-samples/kore_normal.wav"></audio> |
| 高め (x1.15) | <audio controls src="assets/voice-samples/kore_high.wav"></audio> |
| 低め (x0.85) | <audio controls src="assets/voice-samples/kore_low.wav"></audio> |

---

## Leda（現在使用中）

| パターン | 再生 |
|---------|------|
| ノーマル | <audio controls src="assets/voice-samples/leda_normal.wav"></audio> |
| 高め (x1.15) | <audio controls src="assets/voice-samples/leda_high.wav"></audio> |
| 低め (x0.85) | <audio controls src="assets/voice-samples/leda_low.wav"></audio> |

---

## Puck

| パターン | 再生 |
|---------|------|
| ノーマル | <audio controls src="assets/voice-samples/puck_normal.wav"></audio> |
| 高め (x1.15) | <audio controls src="assets/voice-samples/puck_high.wav"></audio> |
| 低め (x0.85) | <audio controls src="assets/voice-samples/puck_low.wav"></audio> |

---

## 再生成方法

```bash
.venv/bin/python scripts/generate_voice_samples.py
```
