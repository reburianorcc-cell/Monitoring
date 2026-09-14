create extension if not exists pgcrypto;

-- CLUP uses the portal's existing Supabase Auth users and public.accounts table.
create table if not exists public.clup_dashboards (
  name text primary key,
  source_name text,
  master_data jsonb not null default '[]'::jsonb,
  locational_data jsonb not null default '[]'::jsonb,
  reclassification_data jsonb not null default '[]'::jsonb,
  updated_by text,
  updated_at timestamptz not null default now()
);

create table if not exists public.clup_upload_history (
  id uuid primary key default gen_random_uuid(),
  created_at timestamptz not null default now(),
  username text not null,
  dashboard_name text not null,
  section text not null,
  source_name text
);

alter table public.clup_dashboards enable row level security;
alter table public.clup_upload_history enable row level security;

-- Access is performed by the server-side secret/service key after portal login.
-- No starter records are inserted and existing CLUP records are never reset.
