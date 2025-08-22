## 環境変数
`.env`ファイルを作成し、以下の内容を追加してください。
```
AZURE_OPENAI_ENDPOINT = [your-endpoint]
AZURE_OPENAI_API_KEY = [your-api-key]
PORT=8501
```

## 起動
```
docker compose up --build
```