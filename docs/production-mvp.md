# Production handoff MVP

Open **Manufacturing → Production workspace** in the design workbench, or open
`/production?project=<project-id>` on the running OpenFabro server. The entry saves
the current editor draft before navigating. The production workflow is independent
of Flux editor development and never rewrites saved design versions.

## Buyer workflow

1. Choose PCB, assembled PCBA, or complete-device scope, batch quantity and country.
2. Generate an estimate. Optional AI cost analysis uses the existing signed-in
   Codex CLI. Arithmetic comes from sourced price evidence; the model explains
   omissions and possible savings. Unknown component/device prices remain unknown.
3. Freeze the production package. A current native PCB can export Gerbers, drills,
   BOM and placement files using the installed KiCad CLI. Alternatively select
   reviewed project files and attest that they belong to this design version.
   Add enclosure/firmware/assembly files and a functional test plan where relevant.
4. Download and inspect the frozen ZIP. It contains the exact file bytes, a design
   snapshot, file SHA-256 checksums, scope, quantity, design version and engineering
   findings. Later edits do not change an existing package.
5. Choose JLCPCB or PCBWay and prepare an RFQ. The target budget is separate from
   the estimate and from the supplier's eventual offer. Each supplier gets its own
   inquiry and its own seven-day, revocable access link.
6. Send the relevant frozen files through the supplier's official quotation page,
   or send the portal link to an actual supplier contact. Record the external
   handoff reference only after sending. Preparing an RFQ does not contact a factory.
7. Review the supplier's itemized offer, validity and lead time, then accept its
   latest offer. Acceptance records your decision; payment and a formal factory
   purchase order still follow the supplier's process.
8. Follow the timeline through engineering review, materials, production, testing
   and shipment. Supplier updates can include carrier and tracking number.

The supplier can open the scoped link, download this package, quote or decline,
and report production after a quote is accepted. A link-holder's claimed company
and contact are labelled as self-declared; this is not an API-verified factory identity.

## What is connected today

Both suppliers have vendor-specific upload instructions, official quotation links,
package checks, independent RFQs, supplier portals, quote acceptance and persistent
progress records. No supplier account or key is created by this feature.

**Direct factory APIs are not enabled in this MVP.** JLCAPI requires an approved
developer account and verification of the applicable service scope. PCBWay's
public partner documentation describes a test environment; production credentials,
authentication and access must be confirmed with PCBWay. The UI states this status.
The sync action returns an explicit setup-required response and preserves the
record. It never invents an external order number, a received package or a payment.
See [official API research and onboarding requirements](production-supplier-apis.md).

An outside supplier must be able to reach your OpenFabro server. A localhost URL
works only on your computer. Opening this page does not deploy a public service or
change your network settings. The supplier portal grants access only to its RFQ and
frozen package; workspace authentication and project roles continue to guard the
rest of the application.

## Evidence and limits

- Estimates use the existing JLCPCB reference-rate table. PCBWay needs its own
  supplier offer; the reference estimate must not be presented as PCBWay's quote.
- Current BOM prices are reused only with matching design, quantity and recent
  evidence. Missing unit prices are not treated as zero. Existing Manufacturing
  stock/quote tools can obtain additional component evidence.
- Taxes, duties, destination surcharges, tooling, unusual fabrication features,
  assembly/test engineering and supplier changes require explicit confirmation.
  No unsupported prediction interval is shown.
- Complete-device estimates explicitly retain enclosure, programming, testing,
  final assembly and packaging costs as unknown until quoted.
- File completeness means ready for supplier review. It does not certify circuit
  functionality, regulatory compliance, a passed physical test or factory acceptance.
- Packages live under each project's hidden `.production/` directory. Its mutable
  records and immutable archives are not exposed to the ordinary Files editor or
  agent file writes. Downloads verify the frozen archive hash.
- Link secrets are stored only as hashes, returned once on issue/rotation, expire
  after seven days and can be revoked. Quote/progress writes support revision
  checks. Mutation idempotency keys reject changed payloads and replay successful
  requests; AI retries are deduplicated before another inference is requested.
- Storage is intended for the existing single-process local server. Multi-process
  deployments need a shared transactional database/lock before scaling writes.

## Validation

```sh
.venv/bin/python -m pytest tests/test_production.py tests/test_production_estimate.py tests/test_production_suppliers.py
npm run test:production
node scripts/browser-checks.mjs --suite=production
```

The browser command starts isolated workspaces and tests real KiCad export, both
supplier inquiries, portal quotation, buyer acceptance, shipment tracking, link
revocation and responsive layout. It removes only its own temporary projects.
The test never contacts a factory, spends money or claims a physical shipment.

The implementation contract is in [production-mvp-contract.md](production-mvp-contract.md).
