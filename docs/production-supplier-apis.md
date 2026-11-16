# Supplier access and handoff

Verified against official sources on November 12, 2026. The production MVP works
through exported production packages and scoped supplier reply links. Its supplier
adapter does not submit files, create factory orders, pay, or poll unverified APIs.

## JLCPCB

[JLCAPI](https://api.jlcpcb.com/) advertises PCB quotes, ordering and tracking,
stencils, 3D printing and components. Its onboarding requires an API-access
application and an application registration. The public page is evidence that an
API exists; it is not evidence that this workspace has permission or that PCBA
quotation and all needed authentication details are available to it.

The MVP therefore returns `api_available: false` and `manual_handoff`, with the
[official quote page](https://cart.jlcpcb.com/quote). Apply for access in JLC's
developer portal and obtain the approved account's current authentication,
environment URLs, quotation/order schemas and PCBA scope before enabling a live
adapter. Do not use browser-session cookies as an undocumented integration.

[JLC's official KiCad export guide](https://jlcpcb.com/help/article/how-to-generate-the-bom-and-centroid-file-from-kicad)
specifies BOM values, references, footprints and JLC/LCSC part numbers. CPL data
contains reference, X/Y in millimetres, rotation and board side. Review part
matching, availability and orientation in the supplier preview before ordering.

## PCBWay

[PCBWay partner Help](https://api-partner.pcbway.com/Help) explicitly labels the
published service as a test environment. It lists PCB quotation, cart/order,
shipping, SMT quotation and fabrication-status methods. Its
[partner workflow PDF](https://api-partner.pcbway.com/PCBWay%20API%20for%20Partners.pdf)
describes quoting, adding to cart, reviewing, paying and tracking as separate steps.
The public documents inspected do not establish production authentication or
approved access for this workspace. No production host or signing algorithm is
guessed in the MVP.

The public [QueryOrderProcess schema](https://api-partner.pcbway.com/Help/Api/POST-api-Pcb-QueryOrderProcess)
accepts `OrderNo` and returns required and completed fabrication processes. It is
evidence for a future read-only adapter after PCBWay confirms production access;
it does not justify treating the test endpoint as a production tracking service.

The MVP uses the [official assembly quote page](https://www.pcbway.com/pcb-assembly.html)
or [bare-board quote page](https://www.pcbway.com/orderonline.aspx).
[Official assembly-file requirements](https://www.pcbway.com/assembly-file-requirements.html)
call for Gerbers, a CSV/Excel BOM and pick-and-place data. Turnkey sourcing needs
manufacturer part-number information. References, orientation and polarity must
be unambiguous; provide an assembly drawing when the silkscreen is insufficient.

## Observable states

`prepare_handoff()` returns `prepared` and `transmitted: false`; it performs no
network access. The buyer must actually upload/send the production package before
recording an external reference. Portal replies carry the provenance of the link
holder, not verified vendor identity. Final assembly, firmware and functional
testing for a complete device need an explicitly agreed scope with the supplier.

`sync_order()` raises `SupplierSetupError` until a verified production adapter is
implemented. Setting key-like environment variables does not make it appear
connected. Exceptions and public profiles contain no credential values or raw
supplier references. Supplier-portal progress remains available without an API.
