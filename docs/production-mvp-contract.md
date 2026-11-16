# Production MVP integration contract

This module is developed beside the Flux editor. It owns `wholeboard/production/`,
`wholeboard/web/production.*`, production tests and documentation. It does not edit
saved circuit designs or their history. Server registration and one Manufacturing
drawer link are the only editor integration points.

## Buyer API

All project routes use `/api/projects/{pid}/production` and existing workspace roles.

- `GET /`: `{project:{id,title,version}, access:{can_edit}, suppliers:[], packages:[],
  estimates:[], rfqs:[], available_files:[{path,role,size}], ai:{ready,provider,label}}`.
- `POST /estimates`: `{base_version,quantity,assembly,shipping_country,use_ai}`;
  returns estimate `{id,source_version,spec_sha256,created_at,quantity,currency,
  line_items:[{item,amount,source}],known_total,total,range_low,range_high,complete,
  unknowns:[],assumptions:[],ai:{status,provider,summary,risks:[],suggestions:[]}}`.
  Null totals mean incomplete evidence, never a free component or a factory price.
- `POST /packages`: `{base_version,scope:'pcb'|'pcba'|'device',quantity,
  files:[{path,role}],test_plan,notes,files_match_design:true}` freezes allowlisted
  project files; no `files` requests export from a current native PCB. Returns
  `{id,source_version,spec_sha256,scope,quantity,created_at,files:[],missing_roles:[],
  readiness,archive_sha256,download_url,checks}`. Inspection and inquiry are allowed
  with disclosed engineering findings; this never certifies a functioning product.
- `GET /packages/{id}/download`: immutable ZIP, verified against recorded hashes.
- `POST /rfqs`: `{package_id,supplier_id,estimate_id?,target_budget?,currency:'USD',
  notes?,contact_email?}` returns RFQ and `supplier_url` once. State is `prepared`.
- `POST /rfqs/{id}/submit`: `{channel:'manual',sent:true,external_reference,notes?}`
  records the user's actual external handoff. Never claims a factory API receipt.
- `POST /rfqs/{id}/invite`: rotate a seven-day capability link; old link is revoked.
- `POST /rfqs/{id}/revoke`: revoke the supplier link.
- `POST /rfqs/{id}/accept`: `{quote_id}` accepts a current unexpired quote; no payment.
- `POST /rfqs/{id}/sync`: official progress if a verified adapter is configured;
  otherwise explicit 409 with a manual-portal alternative.

Mutation request bodies may include `idempotency_key`; reusing it with a different
payload returns 409. Every record includes an integer `revision` for stale-write
guards (`base_revision` for existing RFQs).

RFQ fields include `{id,supplier_id,package_id,status,revision,created_at,quotes:[],
accepted_quote_id,events:[],contact_email,external_reference}`. Statuses:
`prepared`, `submitted`, `quoted`, `accepted`, `engineering_review`, `materials`,
`production`, `testing`, `shipped`, `delivered`, `on_hold`, `declined`, `cancelled`.

## Supplier portal

`/production?project={pid}` is the buyer page. `/production/supplier/{token}` is a
separate capability-scoped page. Public APIs under
`/api/production/supplier/{token}` permit access to that RFQ only:

- `GET /`: `{rfq,package,supplier,project_title}`; no full project or other RFQs.
- `GET /package`: the frozen ZIP.
- `POST /quote`: `{base_revision,decision:'quote'|'decline',supplier_name,
  contact_name,reference,currency,line_items:[{item,amount}],lead_time_days,
  valid_until:'YYYY-MM-DD',notes}`. Total is calculated server-side.
- `POST /events`: `{base_revision,status,note,tracking_number?,carrier?}`.
  Production stages require an accepted quote; no silent backward transitions.

Tokens are stored as hashes, expire, and can be revoked. A portal reply means the
holder of that link replied; vendor identity is self-declared, not API-verified.
Sharing requires the running server to be reachable by the supplier. No outbound
email, payment or production order is triggered automatically.

## Worker interfaces

`estimate.build_estimate(spec, options, *, current_quote=None, stock=None, ai=True)`
returns the estimate value above (caller stamps ID/source version/hash/time).
`estimate.ai_status()` returns redacted readiness. Existing Codex sign-in is
authorized by the user; no new key is created. AI explains costs and unknowns,
while arithmetic and known price evidence stay deterministic.

`suppliers.profiles()` returns supplier metadata; `suppliers.prepare_handoff(id,
rfq,package)` returns explicit manual handoff information. Real quote/progress
methods may be added only from verified official authentication and schemas;
unavailable credentials must fail closed without an invented remote receipt.
