# Decision Log

## 1. Audit Strategy

The audit system was designed around deterministic, high-confidence checks first, followed by contract-specific checks where they could be implemented reliably.

Hospital 1 was used as the labelled development set. The final approach achieved 97.04% accuracy on 913 labelled invoices.

## 2. High-Confidence Rules

The following rules were prioritized because they can be evaluated directly from invoice, line-item, and contract data:

- Contract number validation
- Duplicate invoice ID detection
- Service-date validation
- Line-total arithmetic validation
- Invoice-total arithmetic validation
- Duplicate service billing detection
- Daily quantity cap detection where service matching was sufficiently reliable

These checks produced strong results on Hospital 1, particularly for invoice metadata, dates, arithmetic errors, duplicates, and daily caps.

## 3. Contract Pricing Rules

The contracts also contain more complex pricing rules, including:

- Facility multipliers
- Plan-tier multipliers
- Threshold premiums
- Non-business-day uplifts
- Bundled services
- Cumulative volume discounts
- Exclusion windows

Hospital 1 evaluation showed that these rules are more sensitive to free-text service matching and sequential pricing calculations.

To avoid confidently incorrect predictions, uncertain fuzzy matching was not used as the primary basis for final predictions.

## 4. Hospital Selection

Hospitals 4 and 5 were prioritized for the final submission.

The final coverage is:

- Hospital 4: 835 unique invoices
- Hospital 5: 1,050 unique invoices
- Total: 1,885 unique invoices
- Flagged: 87 invoices

Hospital 1 was not included in submission.csv because it is the labelled development dataset.

## 5. Confidence Strategy

Flagged invoices produced by deterministic checks were assigned higher confidence.

Invoices without detected high-confidence violations were assigned lower confidence because the full contract-pricing engine was not applied to every complex pricing condition.

Expected totals were only populated when a corrected total could be derived directly from invoice arithmetic. Values were left blank where calculating an expected total would require uncertain assumptions.

## 6. Final Trade-off

The implementation prioritizes precision, reproducibility, and explainability over aggressive coverage.

This decision was based on the evaluation result from Hospital 1 and the higher cost of confidently incorrect extraction or contract interpretation.
