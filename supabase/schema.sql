-- Supabase SQL Editor에서 실행

create table if not exists members (
  id uuid primary key default gen_random_uuid(),
  display_name text not null,
  team_code text not null,
  max_rank int not null default 50,
  created_at timestamptz not null default now(),
  unique (display_name, team_code)
);

create table if not exists watchlist_items (
  id uuid primary key default gen_random_uuid(),
  member_id uuid not null references members(id) on delete cascade,
  place_id text not null,
  place_url text not null,
  place_name text not null default '',
  keyword text not null,
  rank int,
  prev_rank int,
  found boolean not null default false,
  changed boolean not null default false,
  updated_at timestamptz,
  created_at timestamptz not null default now(),
  unique (member_id, place_id, keyword)
);

create index if not exists idx_watchlist_member on watchlist_items(member_id);
create index if not exists idx_watchlist_keyword on watchlist_items(keyword);
