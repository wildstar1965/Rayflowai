-- Apply in the Supabase SQL editor before starting the hosted backend.
-- Guest sessions are authenticated by FastAPI's HttpOnly cookie, never by a
-- public service-role credential. Private records are accessible only to the
-- backend; optional signed-in collaboration can read permitted project records.
create table if not exists public.rayflow_records (
  collection text not null,
  id text not null,
  owner_id text not null,
  payload jsonb not null default '{}'::jsonb,
  revision bigint not null default 1 check (revision > 0),
  updated double precision not null default extract(epoch from now()),
  primary key (collection, id)
);
create index if not exists rayflow_records_owner on public.rayflow_records(owner_id, collection, updated desc);
alter table public.rayflow_records enable row level security;
revoke all on public.rayflow_records from anon, authenticated;
grant all on public.rayflow_records to service_role;

create table if not exists public.rayflow_workspace_members (
  workspace_id uuid not null,
  user_id uuid not null references auth.users(id) on delete cascade,
  role text not null default 'editor' check (role in ('owner', 'editor', 'viewer')),
  created_at timestamptz not null default now(),
  primary key (workspace_id, user_id)
);
alter table public.rayflow_workspace_members enable row level security;
create policy "Members can inspect their own membership"
  on public.rayflow_workspace_members for select to authenticated
  using (user_id = auth.uid());
grant select on public.rayflow_workspace_members to authenticated;
grant all on public.rayflow_workspace_members to service_role;

insert into storage.buckets(id, name, public)
values ('rayflow-private', 'rayflow-private', false)
on conflict (id) do update set public = false;
-- No public object policy. FastAPI issues owner-scoped, short-lived signed URLs.

comment on table public.rayflow_records is
  'Rayflow guest sessions, projects, assets, preferences, encrypted credentials and jobs. Never grant anonymous table access.';
