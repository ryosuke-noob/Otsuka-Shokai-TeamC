import whisper
import os

# アプリケーションで使用しているモデル名を指定
MODEL_NAME = "turbo"

print(f"Downloading Whisper model: '{MODEL_NAME}'...")

# モデルをダウンロードしてキャッシュに保存
# キャッシュはコンテナ内のデフォルトパス（例: /root/.cache/whisper）に保存されます
whisper.load_model(MODEL_NAME)

print("Model downloaded and cached successfully.")