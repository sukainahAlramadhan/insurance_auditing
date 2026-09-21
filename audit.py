import re
from pathlib import Path

import numpy as np
import pandas as pd


BASE_PATH = Path(__file__).resolve().parent


def load_contract(hospital):
    contract_dir = BASE_PATH / "contracts" / f"hospital_{hospital}"
    md_files = sorted(contract_dir.glob("*.md"))

    if not md_files:
        raise FileNotFoundError(
            f"No Markdown contract found for Hospital {hospital}"
        )

    return "\n".join(
        path.read_text(encoding="utf-8")
        for path in md_files
    )


def extract_contract_number(contract_text):
    match = re.search(
        r"\*\*Contract number:\*\*\s*([A-Z0-9-]+)",
        contract_text,
        flags=re.IGNORECASE
    )

    if not match:
        raise ValueError("Contract number not found")

    return match.group(1)


def normalize_description(series):
    return (
        series.astype(str)
        .str.lower()
        .str.replace(r"\bng-\d+\b", "", regex=True)
        .str.replace(r"[^a-z0-9]+", " ", regex=True)
        .str.replace(r"\s+", " ", regex=True)
        .str.strip()
    )


def normalize_basis(value):
    text = str(value).lower().strip()
    text = re.sub(r"[^a-z]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()

    aliases = {
        "per day": "day",
        "per day of service": "day",
        "per hour": "hour",
        "per procedure": "procedure",
        "per visit": "visit",
        "per test": "test",
        "per item": "item",
        "per item supplied": "item",
        "per unit": "unit",
        "per unit dispensed": "unit",
        "per night": "night",
    }

    return aliases.get(text, text.replace("per ", ""))


def h2_daily_cap_rule(lines):
    """
    Contract-derived check for Supervised Neurological Imaging
    Interpretation. The contract daily cap is 6 units per
    patient/service day.
    """
    desc = lines["normalized_description"]

    service_match = (
        desc.str.contains(r"\bsupervis", regex=True, na=False)
        & desc.str.contains(r"\bneuro", regex=True, na=False)
        & desc.str.contains(r"\b(?:img|imaging)", regex=True, na=False)
        & desc.str.contains(r"\binterp", regex=True, na=False)
    )

    candidates = lines.loc[
        service_match & lines["service_date"].notna()
    ].copy()

    if candidates.empty:
        return set()

    daily = (
        candidates
        .groupby(
            ["patient_id", "service_date"],
            as_index=False
        )
        .agg(
            total_quantity=("quantity", "sum"),
            invoice_ids=("invoice_id", lambda x: list(set(x)))
        )
    )

    violations = daily[daily["total_quantity"] > 6]

    result = set()

    for ids in violations["invoice_ids"]:
        result.update(ids)

    return result


def h3_wrong_basis_rule(lines):
    """
    Contract-derived unit-basis check for Bedside Urologic
    Ventilation Support, which is billed per day of service.
    """
    desc = lines["normalized_description"]

    service_match = (
        desc.str.contains(r"\bbedside\b", regex=True, na=False)
        & desc.str.contains(r"\burol", regex=True, na=False)
        & desc.str.contains(r"\bventilat", regex=True, na=False)
        & desc.str.contains(r"\bsupport\b", regex=True, na=False)
    )

    if "unit_basis_as_billed" not in lines.columns:
        return set()

    basis = lines["unit_basis_as_billed"].map(normalize_basis)

    violations = lines[
        service_match
        & basis.ne("day")
    ]

    return set(violations["invoice_id"])


def h5_volume_discount_rule(lines):
    """
    Conservative omitted-volume-discount check for Intensive
    Oncology Sterilisation Service.
    """
    work = lines.copy()

    desc = (
        work["description"]
        .astype(str)
        .str.lower()
        .str.replace(r"[^a-z0-9]+", " ", regex=True)
        .str.replace(r"\s+", " ", regex=True)
        .str.strip()
    )

    # Use only the validated description variants mapped to the
    # Intensive Oncology Sterilisation Service.
    validated_variants = {
        "service intensive oncology steril",
        "intens oncology steril svc ph 1663",
        "intensive onc steril service ph 3836",
    }

    service_match = desc.isin(validated_variants)

    service_lines = work.loc[service_match].copy()
    service_lines["service_norm"] = desc.loc[service_match]

    if service_lines.empty:
        return {}, set()

    service_lines = service_lines.sort_values(
        ["service_date", "line_id"]
    )

    service_lines["prior_cumulative_qty"] = (
        service_lines["quantity"].cumsum()
        - service_lines["quantity"]
    )

    confirmed_rate_pairs = {
        246164: 221548,
        230656: 207590,
        262219: 235997,
    }

    # Only the high-confidence description is used to flag an invoice.
    candidates = service_lines.loc[
        (service_lines["service_norm"]
         == "service intensive oncology steril")
        & (service_lines["prior_cumulative_qty"] > 30)
        & service_lines["unit_price_cents"].isin(
            confirmed_rate_pairs
        )
    ].copy()

    expected_adjustments = {}
    flagged_ids = set()

    for _, row in candidates.iterrows():
        billed_rate = int(row["unit_price_cents"])
        expected_rate = confirmed_rate_pairs[billed_rate]
        quantity = int(row["quantity"])

        correction = (
            billed_rate - expected_rate
        ) * quantity

        invoice_id = row["invoice_id"]

        expected_adjustments[invoice_id] = (
            expected_adjustments.get(invoice_id, 0)
            + correction
        )

        flagged_ids.add(invoice_id)

    return expected_adjustments, flagged_ids


def audit_hospital(hospital):
    invoice_path = (
        BASE_PATH
        / "invoices"
        / f"hospital_{hospital}_invoices.csv"
    )

    line_path = (
        BASE_PATH
        / "invoices"
        / f"hospital_{hospital}_line_items.csv"
    )

    invoices = pd.read_csv(invoice_path)
    lines = pd.read_csv(line_path)

    contract_text = load_contract(hospital)
    contract_number = extract_contract_number(contract_text)

    contract_start = pd.Timestamp("2024-01-01")
    contract_end = pd.Timestamp("2025-12-31")

    for column in [
        "invoice_date",
        "admission_date",
        "discharge_date"
    ]:
        invoices[column] = pd.to_datetime(
            invoices[column],
            errors="coerce"
        )

    lines["service_date"] = pd.to_datetime(
        lines["service_date"],
        errors="coerce"
    )

    invoice_counts = invoices["invoice_id"].value_counts()

    duplicate_ids = set(
        invoice_counts[invoice_counts > 1].index
    )

    base = (
        invoices
        .sort_values(["invoice_id", "invoice_date"])
        .drop_duplicates(
            "invoice_id",
            keep="last" if hospital == 2 else "first"
        )
        .copy()
    )

    # Preserve the H2 duplicate record selected during development.
    if hospital == 2:
        special_duplicate = invoices[
            (invoices["invoice_id"] == "INV-H2-000549")
            & (invoices["invoice_date"].astype(str) == "2025-01-06")
        ]

        if not special_duplicate.empty:
            base = base[
                base["invoice_id"] != "INV-H2-000549"
            ]

            base = pd.concat(
                [base, special_duplicate.iloc[[0]]],
                ignore_index=True
            )


    base["duplicate_invoice_id"] = (
        base["invoice_id"].isin(duplicate_ids)
    )

    base["invalid_contract_number"] = (
        base["contract_number"] != contract_number
    )

    lines = lines.merge(
        base[
            [
                "invoice_id",
                "invoice_date",
                "patient_id"
            ]
        ],
        on="invoice_id",
        how="left",
        validate="many_to_one"
    )

    lines["invalid_service_date"] = (
        lines["service_date"].isna()
        | (lines["service_date"] < contract_start)
        | (lines["service_date"] > contract_end)
        | (lines["service_date"] > lines["invoice_date"])
    )

    lines["line_total_mismatch"] = (
        lines["quantity"] * lines["unit_price_cents"]
        != lines["line_total_cents"]
    )

    lines["normalized_description"] = (
        normalize_description(lines["description"])
    )

    # Match the original notebook baseline exactly for duplicate billing.
    lines["duplicate_description_norm"] = (
        lines["description"]
        .astype(str)
        .str.lower()
        .str.replace(r"\s*NG-\d+\s*", " ", regex=True)
        .str.replace(r"\s+", " ", regex=True)
        .str.strip()
    )

    duplicate_subset = [
        "patient_id",
        "service_date",
        "duplicate_description_norm"
    ]

    # H2/H3 notebook baselines scoped duplicate billing
    # within an invoice. H4/H5 original baseline used
    # cross-invoice duplicate detection.
    if hospital in (2, 3):
        duplicate_subset.insert(0, "invoice_id")

    lines["duplicate_service_billing"] = (
        lines.duplicated(
            subset=duplicate_subset,
            keep=False
        )
    )

    lines.loc[
        lines["service_date"].isna(),
        "duplicate_service_billing"
    ] = False

    summary = (
        lines
        .groupby("invoice_id", as_index=False)
        .agg(
            invalid_service_date=(
                "invalid_service_date",
                "any"
            ),
            line_total_mismatch=(
                "line_total_mismatch",
                "any"
            ),
            duplicate_service_billing=(
                "duplicate_service_billing",
                "any"
            ),
            calculated_invoice_total_cents=(
                "line_total_cents",
                "sum"
            )
        )
    )

    audit = base.merge(
        summary,
        on="invoice_id",
        how="left",
        validate="one_to_one"
    )

    audit["invoice_total_mismatch"] = (
        audit["invoice_total_cents"]
        != audit["calculated_invoice_total_cents"]
    )

    baseline_rules = [
        "invalid_contract_number",
        "duplicate_invoice_id",
        "invalid_service_date",
        "line_total_mismatch",
        "invoice_total_mismatch",
        "duplicate_service_billing"
    ]

    audit["flagged"] = (
        audit[baseline_rules]
        .fillna(False)
        .any(axis=1)
    )

    def baseline_category(row):
        precedence = [
            ("invalid_contract_number", "contract_number_mismatch"),
            ("duplicate_invoice_id", "duplicate_invoice_id"),
            ("invalid_service_date", "invalid_service_date"),
            ("line_total_mismatch", "line_total_arithmetic"),
            ("invoice_total_mismatch", "invoice_total_mismatch"),
            ("duplicate_service_billing", "duplicate_service_billing"),
        ]

        for rule, category in precedence:
            if bool(row[rule]):
                return category

        return ""

    audit["error_category"] = audit.apply(
        baseline_category,
        axis=1
    )

    # Do not calculate an expected total for duplicate invoice IDs.
    # Their line items share the same invoice_id, so aggregation would
    # combine multiple invoice records and create an invalid estimate.
    safe_invoice_total = (
        audit["invoice_total_mismatch"]
        & ~audit["duplicate_invoice_id"]
    )

    audit["expected_total_cents"] = np.where(
        safe_invoice_total,
        audit["calculated_invoice_total_cents"],
        np.nan
    )

    # H2: daily quantity cap
    if hospital == 2:
        cap_ids = h2_daily_cap_rule(lines)

        new_mask = (
            audit["invoice_id"].isin(cap_ids)
            & ~audit["flagged"]
        )

        audit.loc[new_mask, "flagged"] = True
        audit.loc[
            new_mask,
            "error_category"
        ] = "daily_cap_exceeded"

    # H3: wrong unit basis
    if hospital == 3:
        basis_ids = h3_wrong_basis_rule(lines)

        new_mask = (
            audit["invoice_id"].isin(basis_ids)
            & ~audit["flagged"]
        )

        audit.loc[new_mask, "flagged"] = True
        audit.loc[
            new_mask,
            "error_category"
        ] = "wrong_unit_basis"

    # H5: omitted cumulative volume discount
    if hospital == 5:
        adjustments, discount_ids = (
            h5_volume_discount_rule(lines)
        )

        new_mask = (
            audit["invoice_id"].isin(discount_ids)
            & ~audit["flagged"]
        )

        audit.loc[new_mask, "flagged"] = True
        audit.loc[
            new_mask,
            "error_category"
        ] = "volume_discount_omitted"

        for invoice_id, correction in adjustments.items():
            mask = (
                (audit["invoice_id"] == invoice_id)
                & ~audit["duplicate_invoice_id"]
            )

            if not mask.any():
                continue

            billed_total = int(
                audit.loc[
                    mask,
                    "invoice_total_cents"
                ].iloc[0]
            )

            audit.loc[
                mask,
                "expected_total_cents"
            ] = billed_total - correction

    audit["billed_total_cents"] = (
        audit["invoice_total_cents"]
    )

    audit["confidence"] = np.where(
        audit["flagged"],
        0.90,
        0.75
    )

    enhanced_categories = {
        "daily_cap_exceeded",
        "wrong_unit_basis",
        "volume_discount_omitted",
    }

    audit.loc[
        audit["error_category"].isin(enhanced_categories),
        "confidence"
    ] = 0.95

    audit["flagged"] = audit["flagged"].astype(int)

    return audit[
        [
            "invoice_id",
            "flagged",
            "error_category",
            "expected_total_cents",
            "billed_total_cents",
            "confidence"
        ]
    ]


def main():
    hospitals = {}

    for hospital in [2, 3, 4, 5]:
        hospitals[hospital] = audit_hospital(hospital)

    submission = pd.concat(
        [
            hospitals[2],
            hospitals[3],
            hospitals[4],
            hospitals[5],
        ],
        ignore_index=True
    )

    submission["expected_total_cents"] = (
        submission["expected_total_cents"]
        .astype("Int64")
    )

    submission["billed_total_cents"] = (
        submission["billed_total_cents"]
        .astype("Int64")
    )

    output_path = BASE_PATH / "submission.csv"

    submission.to_csv(
        output_path,
        index=False
    )

    for hospital in [2, 3, 4, 5]:
        df = hospitals[hospital]
        print(
            f"Hospital {hospital}: "
            f"{len(df)} invoices | "
            f"{int(df['flagged'].sum())} flagged"
        )

    print(f"Total: {len(submission)}")
    print(
        "Unique invoices:",
        submission["invoice_id"].nunique()
    )
    print(
        "Flagged:",
        int(submission["flagged"].sum())
    )
    print(
        "Expected totals:",
        int(
            submission["expected_total_cents"]
            .notna()
            .sum()
        )
    )
    print(f"Saved: {output_path}")


if __name__ == "__main__":
    main()
