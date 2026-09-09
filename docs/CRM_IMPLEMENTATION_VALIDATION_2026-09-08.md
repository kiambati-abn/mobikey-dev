# CRM implementation validation — 8 September 2026

The final isolated Odoo 19 run completed with **48 tests, zero failures and zero errors**. It installed `mobikey_sale_approvals`, `mobikey_sale_documents` and `synconics_bi_dashboard` with their dependencies in a disposable database. The runner removed that database after completion.

Tested areas include:

- Native CRM movement while quotation approvals are pending.
- Discount boundaries, highest-line routing, discount-before-margin ordering, zero-price handling, financing/trade-in routing and missing company assignments.
- Ordinary salesperson quoting and stocked-product confirmation, plus API/field/aggregate restrictions on product costs, average cost, valuation, supplier price metadata and quotation margins.
- Direct decision-write rejection, assigned-role checks, obsolete decisions, revision history, protected input snapshots, copying and down-payment section creation.
- Explicit internal email recipients, deduplication, no customer recipient, and safe approval outcomes.
- Primary quotation selection, alternatives, amount changes, cancellation, tax basis, currency conversion and quotation pricing-date retention on confirmation.
- Report/composer checkpoints and actual HTTP requests using an existing portal token: document access, signature and payment initiation are blocked before approval.
- Configured confirmation-based commission, duplicate-proof handover, immutable forecast snapshots and a synthetic legacy cutover without duplicate lines or inherited commercial approvals.
- Existing branded/native report HTML and PDF outputs, BI totals, invalid filters, currency requirements and growth/zero-baseline comparisons.

The final run log is [test-20260908-120347.log](/home/ocean/.local/share/odoo-lab/projects/mobikey-crm-workflow-35e0a232/logs/test-20260908-120347.log). Odoo reported 95.05 seconds for post-install tests, excluding installation and setup. `git diff --check` and Python/XML parsing also passed.

This is source and isolated-runtime validation, not a production upgrade rehearsal. The live database, Studio rules, inherited views, historical artifacts, configured payment providers, actual role memberships and production-sized datasets remain uninspected. Invoicing/full-payment commission policies require staging validation once the business selects its milestone. Policy defaults, real thresholds, final dashboards and production rollout remain subject to the decisions and staging work listed in the [implementation guide](/home/ocean/Mobikey-Production/mobikey_sale_approvals/README.md).
