# Audit Prompts

## Contract Analysis Prompt

Analyze the hospital reimbursement contract and extract auditable rules, including:

- Contract number and effective dates
- Base service rates and unit basis
- Daily quantity limits
- Facility and plan-tier multipliers
- Threshold premiums
- Non-business-day uplifts
- Bundled services
- Cumulative volume discounts
- Exclusion windows
- Invoice validation requirements

Prefer deterministic contract rules and explicitly identify rules that require uncertain free-text service matching.

## Invoice Audit Prompt

Audit each invoice against the applicable contract and line-item data.

Prioritize high-confidence checks:

1. Validate the contract number.
2. Detect duplicate invoice IDs.
3. Validate service dates against contract and invoice dates.
4. Validate line-total arithmetic.
5. Validate invoice-total arithmetic.
6. Detect duplicate service billing for the same patient and service date.
7. Apply contract-specific rules only when the required service mapping is sufficiently reliable.

Do not infer a corrected monetary total when the contract evidence is insufficient. Reduce confidence rather than making an unsupported pricing assumption.
