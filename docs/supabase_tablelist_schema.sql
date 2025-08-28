-- docs/DB設計.md の「テーブル一覧（PKとカラム）」準拠スキーマ

create extension if not exists pgcrypto;

do $$ begin
  if not exists (select 1 from pg_type where typname = 'question_status') then
    create type question_status as enum ('unanswered','take_home','answered');
  end if;
end $$;

create or replace function set_updated_at()
returns trigger language plpgsql as $$
begin
  new.updated_at = now();
  return new;
end;$$;

-- customers
create table if not exists public.customers (
  id uuid primary key default gen_random_uuid(),
  name text not null,
  kana_name text,
  phone text,
  email text,
  notes text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create index if not exists customers_name_idx on public.customers(name);
create trigger customers_set_updated_at
before update on public.customers
for each row execute function set_updated_at();

-- conversations
create table if not exists public.conversations (
  id uuid primary key default gen_random_uuid(),
  title text not null,
  customer_company text,
  customer_contact text,
  started_at timestamptz not null default now(),
  closed_at timestamptz,
  updated_at timestamptz not null default now()
);
create trigger conversations_set_updated_at
before update on public.conversations
for each row execute function set_updated_at();

-- notes
create table if not exists public.notes (
  id uuid primary key default gen_random_uuid(),
  conversation_id uuid not null references public.conversations(id) on delete cascade,
  content text not null,
  created_at timestamptz not null default now()
);
create index if not exists notes_conv_idx on public.notes(conversation_id);

-- questions
create table if not exists public.questions (
  id uuid primary key default gen_random_uuid(),
  conversation_id uuid not null references public.conversations(id) on delete cascade,
  question_text text not null,
  status question_status not null default 'unanswered',
  priority integer,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create index if not exists questions_conv_idx on public.questions(conversation_id);
create index if not exists questions_conv_status_idx on public.questions(conversation_id, status);
create trigger questions_set_updated_at
before update on public.questions
for each row execute function set_updated_at();

-- answers
create table if not exists public.answers (
  id uuid primary key default gen_random_uuid(),
  question_id uuid not null unique references public.questions(id) on delete cascade,
  answer_text text not null,
  answered_at timestamptz not null default now()
);
create index if not exists answers_qid_idx on public.answers(question_id);

-- tags
create table if not exists public.tags (
  id uuid primary key default gen_random_uuid(),
  name text not null unique,
  created_at timestamptz not null default now()
);

-- question_tags
create table if not exists public.question_tags (
  question_id uuid not null references public.questions(id) on delete cascade,
  tag_id uuid not null references public.tags(id) on delete cascade,
  primary key (question_id, tag_id)
);
create index if not exists qtags_tag_idx on public.question_tags(tag_id);

-- products
create table if not exists public.products (
  id uuid primary key default gen_random_uuid(),
  name text not null,
  cost integer,
  category text,
  brand text,
  description text,
  created_at timestamptz not null default now()
);
create index if not exists products_name_idx on public.products(name);

-- transcripts
create table if not exists public.transcripts (
  id uuid primary key default gen_random_uuid(),
  conversation_id uuid not null references public.conversations(id) on delete cascade,
  transcript_text text not null,
  created_at timestamptz not null default now()
);
create index if not exists transcripts_conv_idx on public.transcripts(conversation_id);

-- customer_company_profiles
create table if not exists public.customer_company_profiles (
  id uuid primary key default gen_random_uuid(),
  industry_name text,
  website_url text,
  company_size text,
  employment_numbers integer,
  headquarters_address text,
  capital_amount text,
  founded_on date,
  profile_note text,
  updated_at timestamptz not null default now()
);
create trigger company_profiles_set_updated_at
before update on public.customer_company_profiles
for each row execute function set_updated_at();

-- daily_reports（customer_company_profiles 作成後に作成する）
create table if not exists public.daily_reports (
  id uuid primary key default gen_random_uuid(),
  customer_id uuid references public.customers(id) on delete set null,
  company_profile_id uuid references public.customer_company_profiles(id) on delete set null,
  conversation_id uuid references public.conversations(id) on delete set null,
  content text not null,
  created_at timestamptz not null default now()
);
create index if not exists daily_reports_customer_idx on public.daily_reports(customer_id);
create index if not exists daily_reports_company_profile_idx on public.daily_reports(company_profile_id);
create index if not exists daily_reports_conversation_idx on public.daily_reports(conversation_id);


