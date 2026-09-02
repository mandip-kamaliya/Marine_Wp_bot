-- ECHT Marine production foundation. Apply only to the Marine Supabase project.

create extension if not exists pgcrypto;

create or replace function public.set_updated_at()
returns trigger language plpgsql as $$
begin new.updated_at = now(); return new; end;
$$;

create table public.customers (
  id uuid primary key default gen_random_uuid(),
  whatsapp_number text not null unique check (whatsapp_number ~ '^\+?[1-9][0-9]{7,14}$'),
  name text,
  company_name text,
  is_active boolean not null default true,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table public.conversations (
  id uuid primary key default gen_random_uuid(),
  customer_id uuid not null references public.customers(id) on delete restrict,
  business_whatsapp_number text not null check (business_whatsapp_number ~ '^\+?[1-9][0-9]{7,14}$'),
  state text not null default 'new',
  mode text not null default 'bot' check (mode in ('bot','human')),
  flow_context jsonb not null default '{}'::jsonb,
  assigned_team text,
  handover_reason text,
  closed_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create unique index conversations_one_open_per_customer_number_idx
  on public.conversations (customer_id, business_whatsapp_number)
  where closed_at is null;

create table public.messages (
  id uuid primary key default gen_random_uuid(),
  conversation_id uuid not null references public.conversations(id) on delete restrict,
  customer_id uuid not null references public.customers(id) on delete restrict,
  direction text not null check (direction in ('inbound','outbound')),
  message_type text not null default 'text' check (message_type in ('text','interactive','image','video','document','other')),
  content text,
  actions jsonb not null default '[]'::jsonb,
  external_provider text,
  external_message_id text,
  related_inbound_message_id text,
  draft_status text check (draft_status in ('pending','sending','sent','failed','reconciliation_required')),
  send_claim_token text,
  send_claimed_at timestamptz,
  delivery_status text,
  provider_error_code text,
  received_at timestamptz,
  sent_at timestamptz,
  created_at timestamptz not null default now()
);

create unique index messages_provider_idempotency_idx
  on public.messages (external_provider, external_message_id)
  where external_message_id is not null;

create unique index messages_outbound_draft_idempotency_idx
  on public.messages (related_inbound_message_id)
  where direction = 'outbound' and related_inbound_message_id is not null;

create index messages_conversation_created_idx
  on public.messages (conversation_id, created_at desc);

create table public.leads (
  id uuid primary key default gen_random_uuid(),
  customer_id uuid not null references public.customers(id) on delete restrict,
  conversation_id uuid not null references public.conversations(id) on delete restrict,
  idempotency_key text not null unique,
  lead_type text not null,
  priority text not null default 'normal' check (priority in ('normal','high','hot')),
  requirement jsonb not null default '{}'::jsonb,
  status text not null default 'new' check (status in ('new','assigned','contacted','closed')),
  zoho_sync_status text not null default 'pending' check (zoho_sync_status in ('pending','synced','failed','not_required')),
  zoho_lead_id text,
  zoho_attempted_at timestamptz,
  assigned_team text not null default 'marine_sales',
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table public.handovers (
  id uuid primary key default gen_random_uuid(),
  conversation_id uuid not null references public.conversations(id) on delete restrict,
  customer_id uuid not null references public.customers(id) on delete restrict,
  reason text not null,
  assigned_team text not null,
  context_snapshot jsonb not null default '{}'::jsonb,
  status text not null default 'open' check (status in ('open','accepted','resolved')),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (conversation_id, reason)
);

create table public.audit_logs (
  id uuid primary key default gen_random_uuid(),
  action text not null,
  entity_type text not null,
  entity_id uuid,
  details jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

create trigger customers_set_updated_at before update on public.customers
  for each row execute function public.set_updated_at();
create trigger conversations_set_updated_at before update on public.conversations
  for each row execute function public.set_updated_at();
create trigger leads_set_updated_at before update on public.leads
  for each row execute function public.set_updated_at();
create trigger handovers_set_updated_at before update on public.handovers
  for each row execute function public.set_updated_at();

create or replace function public.claim_outbound_draft(p_draft_id uuid, p_claim_token text)
returns boolean language plpgsql security definer set search_path = public as $$
begin
  update public.messages
     set draft_status = 'sending', send_claim_token = p_claim_token, send_claimed_at = now()
   where id = p_draft_id and direction = 'outbound' and draft_status = 'pending'
     and external_message_id is null and send_claim_token is null;
  return found;
end;
$$;

create or replace function public.complete_outbound_draft(
  p_draft_id uuid, p_claim_token text, p_provider_message_id text
)
returns boolean language plpgsql security definer set search_path = public as $$
begin
  update public.messages
     set draft_status = 'sent', delivery_status = 'accepted',
         external_provider = 'exotel', external_message_id = p_provider_message_id,
         sent_at = now()
   where id = p_draft_id and draft_status = 'sending'
     and send_claim_token = p_claim_token and external_message_id is null;
  return found;
end;
$$;

revoke all on function public.claim_outbound_draft(uuid, text) from public, anon, authenticated;
revoke all on function public.complete_outbound_draft(uuid, text, text) from public, anon, authenticated;
grant execute on function public.claim_outbound_draft(uuid, text) to service_role;
grant execute on function public.complete_outbound_draft(uuid, text, text) to service_role;

alter table public.customers enable row level security;
alter table public.conversations enable row level security;
alter table public.messages enable row level security;
alter table public.leads enable row level security;
alter table public.handovers enable row level security;
alter table public.audit_logs enable row level security;

