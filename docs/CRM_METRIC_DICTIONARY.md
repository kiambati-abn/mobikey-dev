# CRM and Sales metric dictionary

| Metric | Grain and population | Date / amount basis | Owner and drill-down |
|---|---|---|---|
| Open pipeline | Active, non-won opportunities, once per opportunity | Current expected revenue; primary quotation or initial estimate in operating-company currency | Sales owner; native opportunities |
| Weighted forecast | Same population | Expected revenue × probability / 100; never multiply native prorated revenue twice | Sales manager; native forecast |
| Primary quotations | Explicit selected current offers; exclude cancelled and alternatives | Quote date; company-selected tax basis and quote-date currency conversion | Sales owner; primary quotation link |
| Confirmed sales | Native confirmed orders, once per order | Confirmation date; native untaxed sales measure, currency-normalised | Sales manager; native Sales Analysis |
| Invoiced revenue | Posted customer invoices less posted credit notes | Accounting invoice date; untaxed company-currency amount | Finance; posted invoice lines |
| Collections | Reconciled customer receivables; count each allocated payment once | Payment/reconciliation policy must be agreed before adding this KPI | Finance; receivable reconciliations |
| Closed-opportunity win rate | Won / (won + lost); fixed closed-date cohort | No result when denominator is zero | Sales manager; closed opportunities |
| Approval turnaround | One decision per quotation revision/category | Requested to decided elapsed hours; distinguish pending and withdrawn revisions | Approval administrator; approval records |
| Historical forecast | One opportunity per daily snapshot | Frozen owner, stage, close date, probability, amount basis, value, currency and rate date | Sales manager; forecast snapshots |

Forecast snapshots and live pipeline are different populations. Never sum snapshots across dates as if they were independent opportunities. Do not join opportunity value to every quotation/order line and then sum it. Native sales totals and CRM Won remain distinct; an opportunity can be moved freely without making a legal customer commitment.

BI monetary tiles convert source currency to the configured company currency using the configured date field (today when no date field is configured). Configure and label that date deliberately. Tiles use the whole filtered population; display/ranking limits do not truncate totals. Period percentage comparison is `(current − previous) / previous × 100`; zero-to-zero is 0%, and a nonzero current value with a zero baseline is N/A.

Median/P90 approval durations, offer-family/cohort conversion, allocated collections, marketing ROI and forecast-versus-actual joins need a reviewed report definition and staging data. Do not present simple averages, lead counts or invoice totals under those labels.
