import os
from dotenv import load_dotenv
from supabase import create_client
from openai import AzureOpenAI

load_dotenv()
supabase = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_SERVICE_ROLE_KEY"))
client = AzureOpenAI(
    azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT"),
    api_key=os.getenv("AZURE_OPENAI_API_KEY"),
    api_version="2024-05-01-preview",
)
deployment = os.getenv("AZURE_EMBEDDING_DEPLOYMENT", "text-embedding-3-large")

# 1) embedding が未設定の行を取得
rows = supabase.table("products").select("id, description").is_("embedding", None).limit(200).execute().data

for row in rows:
    text = (row.get("description") or "").strip()
    if not text:
        continue
    emb = client.embeddings.create(model=deployment, input=text).data[0].embedding
    supabase.table("products").update({"embedding": emb}).eq("id", row["id"]).execute()