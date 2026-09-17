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
        .drop_duplicates("invoice_id", keep="first")
        .copy()
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
        lines["description"]
        .astype(str)
        .str.lower()
        .str.replace(
            r"\bng-\d+\b",
            "",
            regex=True
        )
        .str.replace(
            r"[^a-z0-9]+",
            " ",
            regex=True
        )
        .str.replace(
            r"\s+",
            " ",
            regex=True
        )
        .str.strip()
    )

    lines["duplicate_service_billing"] = (
        lines.duplicated(
            subset=[
                "patient_id",
                "service_date",
                "normalized_description"
            ],
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

    rules = [
        "invalid_contract_number",
        "duplicate_invoice_id",
        "invalid_service_date",
        "line_total_mismatch",
        "invoice_total_mismatch",
        "duplicate_service_billing"
    ]

    audit["flagged"] = (
        audit[rules]
        .fillna(False)
        .any(axis=1)
    )

    def categories(row):
        return "|".join(
            rule
            for rule in rules
            if bool(row[rule])
        )

    audit["error_category"] = audit.apply(
        categories,
        axis=1
    )

    audit["expected_total_cents"] = np.where(
        audit["invoice_total_mismatch"],
        audit["calculated_invoice_total_cents"],
        np.nan
    )

    audit["billed_total_cents"] = (
        audit["invoice_total_cents"]
    )

    audit["confidence"] = np.where(
        audit["flagged"],
        0.90,
        0.75
    )

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
    hospital_4 = audit_hospital(4)
    hospital_5 = audit_hospital(5)

    submission = pd.concat(
        [hospital_4, hospital_5],
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

    print(f"Hospital 4: {len(hospital_4)}")
    print(f"Hospital 5: {len(hospital_5)}")
    print(f"Total: {len(submission)}")
    print(f"Flagged: {submission['flagged'].sum()}")
    print(f"Saved: {output_path}")


if __name__ == "__main__":
    main()
