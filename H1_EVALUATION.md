# Hospital 1 Evaluation Report

## Overview

Hospital 1 was used as the labelled development set to evaluate the audit approach before applying it to the unlabelled hospitals.

The final Hospital 1 audit achieved:

- Invoices evaluated: 913
- Accuracy: 97.04%
- True Positives: 37
- True Negatives: 849
- False Positives: 6
- False Negatives: 21

## Per-Category Performance

| Error Category | Cases | Detected | Recall |
|---|---:|---:|---:|
| unknown_service | 12 | 4 | 33.3% |
| wrong_unit_basis | 11 | 5 | 45.5% |
| unit_price_mismatch | 10 | 3 | 30.0% |
| invoice_total_mismatch | 6 | 6 | 100.0% |
| line_total_arithmetic | 6 | 6 | 100.0% |
| malformed_service_date | 6 | 6 | 100.0% |
| premium_incorrectly_applied | 6 | 3 | 50.0% |
| bundle_not_applied | 5 | 3 | 60.0% |
| contract_number_mismatch | 5 | 5 | 100.0% |
| duplicate_invoice_id | 5 | 5 | 100.0% |
| service_date_after_invoice_date | 5 | 5 | 100.0% |
| service_date_out_of_window | 5 | 5 | 100.0% |
| cross_invoice_duplicate | 4 | 4 | 100.0% |
| daily_cap_exceeded | 4 | 4 | 100.0% |
| exclusion_window_violation | 4 | 1 | 25.0% |
| volume_discount_incorrectly_applied | 4 | 2 | 50.0% |
| volume_discount_omitted | 4 | 1 | 25.0% |
| premium_omitted | 3 | 0 | 0.0% |

## Systematic Error Analysis

The strongest results came from deterministic invoice-level and arithmetic checks. Contract-number mismatches, duplicate invoice IDs, invalid service dates, line-total arithmetic errors, invoice-total mismatches, cross-invoice duplicates, and daily-cap violations were detected reliably.

The main false-negative patterns were contract-pricing errors that require reliable mapping between free-text line-item descriptions and contract services. These included unknown services, wrong unit basis, unit-price mismatches, premiums, bundles, exclusion windows, and cumulative volume discounts.

The system therefore prioritizes high-confidence deterministic checks over aggressive fuzzy contract matching. This reduces the risk of confidently flagging valid invoices because of uncertain service-name matching.

## Application to Unlabelled Hospitals

The validated high-confidence approach was applied to Hospitals 4 and 5. Predictions were generated for 1,885 unique invoices:

- Hospital 4: 835 invoices
- Hospital 5: 1,050 invoices
- Total flagged: 87

Contract-pricing rules requiring uncertain service matching were intentionally treated conservatively.
