## テーブル一覧（PKとカラム）

- **conversations**
  - PK: `id` (uuid) — 商談の一意なID
  - `title` (text, not null) — 商談タイトル
  - `customer_company` (text) — 顧客企業名
  - `customer_contact` (text) — 顧客担当者名
  - `started_at` (timestamptz, default now()) — 商談開始日時
  - `closed_at` (timestamptz) — 商談終了日時（任意）
  - `updated_at` (timestamptz, default now()) — レコード更新日時

- **notes**
  - PK: `id` (uuid) — メモの一意なID
  - `conversation_id` (uuid, not null, unique, FK → conversations.id, on delete cascade) — 紐づく商談ID（1対1）
  - `content` (text, not null) — メモ本文
  - `created_at` (timestamptz, default now()) — 作成日時

- **questions**
  - PK: `id` (uuid) — 質問の一意なID
  - `conversation_id` (uuid, not null, FK → conversations.id, on delete cascade) — 紐づく商談ID
  - `question_text` (text, not null) — 質問文
  - `status` (question_status, not null, default 'unanswered') — 状態（unanswered/take_home/answered）
  - `priority` (integer) — 優先度（数値が大きいほど優先）
  - `created_at` (timestamptz, default now()) — 作成日時
  - `updated_at` (timestamptz, default now()) — 更新日時

- **answers**
  - PK: `id` (uuid) — 回答の一意なID
  - `question_id` (uuid, not null, unique, FK → questions.id, on delete cascade) — 紐づく質問ID（1対1）
  - `answer_text` (text, not null) — 回答本文
  - `answered_at` (timestamptz, default now()) — 回答日時

- **tags**
  - PK: `id` (uuid) — タグの一意なID
  - `name` (text, not null, unique) — タグ名（ユニーク）
  - `created_at` (timestamptz, default now()) — 作成日時

- **question_tags**
  - PK: (`question_id`, `tag_id`) — 質問とタグの関連を表す複合主キー
  - `question_id` (uuid, not null, FK → questions.id, on delete cascade) — 紐づく質問ID
  - `tag_id` (uuid, not null, FK → tags.id, on delete cascade) — 紐づくタグID

- **customers**
  - PK: `id` (uuid) — 顧客の一意なID
  - `name` (text, not null) — 顧客名
  - `kana_name` (text) — 顧客名（カナ）
  - `phone` (text) — 電話番号
  - `email` (text) — 顧客メール
  - `notes` (text) — 備考
  - `created_at` (timestamptz, default now()) — 作成日時
  - `updated_at` (timestamptz, default now()) — 更新日時

- **daily_reports**
  - PK: `id` (uuid) — 日報の一意なID
  - `customer_id` (uuid, FK → customers.id, on delete set null) — 紐づく顧客ID
  - `company_profile_id` (uuid, FK → customer_company_profiles.id, on delete set null) — 紐づく会社情報ID
  - `conversation_id` (uuid, FK → conversations.id, on delete set null) — 紐づく商談ID（任意）
  - `content` (text, not null) — 日報本文
  - `created_at` (timestamptz, default now()) — 作成日時

- **products**
  - PK: `id` (uuid) — 製品の一意なID
  - `name` (text, not null) — 製品名
  - `cost` (int) - 値段
  - `category` (text) — カテゴリ
  - `brand` (text) — ブランド
  - `description` (text) — 説明
  - `created_at` (timestamptz, default now()) — 作成日時

- **transcripts**（書き起こし）
  - PK: `id` (uuid) — 書き起こしの一意なID
  - `conversation_id` (uuid, not null, FK → conversations.id, on delete cascade) — 紐づく商談ID
  - `transcript_text` (text, not null) — 書き起こし本文
  - `created_at` (timestamptz, default now()) — 作成日時

- **customer_company_profiles**（顧客会社情報）
  - PK: `id` (uuid) — 会社の一意なID
  - `industry_name` (text) — 業種名
  - `website_url` (text) — 企業サイトURL
  - `company_size` (text) — 会社規模
  - `employment_numbers`(int) - 従業員数
  - `headquarters_address` (text) — 本社所在地
  - `capital_amount` (text) — 資本金
  - `founded_on` (date) — 設立日
  - `profile_note` (text) — 会社プロフィールの補足
  - `updated_at` (timestamptz, default now()) — 更新日時