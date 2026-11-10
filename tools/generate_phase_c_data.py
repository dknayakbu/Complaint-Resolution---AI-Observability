from __future__ import annotations

import json
from collections.abc import Iterable, Sequence
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"


CATEGORY_SEQUENCE = [
    "cards_payments",
    "accounts",
    "fraud_scams",
    "lending",
    "service_access",
    "discrimination",
    "other",
]


def write_jsonl(path: Path, rows: Sequence[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, separators=(",", ":")) + "\n")


def build_showcase() -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    complaints = [
        {
            "case_id": "showcase-001",
            "complaint_text": "My debit card was charged twice for the same hotel booking and the duplicate payment still appears on my account.",
            "synthetic": True,
            "source_sample_id": "showcase-001",
        },
        {
            "case_id": "showcase-002",
            "complaint_text": "I cannot access my online account because my password reset email never arrives, and I am locked out.",
            "synthetic": True,
            "source_sample_id": "showcase-002",
        },
        {
            "case_id": "showcase-003",
            "complaint_text": "A transfer from my checking account was sent to the wrong person and I need the funds returned immediately.",
            "synthetic": True,
            "source_sample_id": "showcase-003",
        },
        {
            "case_id": "showcase-004",
            "complaint_text": "My loan payment was incorrectly applied and now my account shows a missed due date despite my payment being made.",
            "synthetic": True,
            "source_sample_id": "showcase-004",
        },
        {
            "case_id": "showcase-005",
            "complaint_text": "The app shows I am locked out of the service and I cannot use my benefits verification page.",
            "synthetic": True,
            "source_sample_id": "showcase-005",
        },
        {
            "case_id": "showcase-006",
            "complaint_text": "I was refused a mortgage because the lender treated me differently after hearing about my disability.",
            "synthetic": True,
            "source_sample_id": "showcase-006",
        },
        {
            "case_id": "showcase-007",
            "complaint_text": "I suspect there is a scam text asking me to transfer funds to a fake account before my payment is processed.",
            "synthetic": True,
            "source_sample_id": "showcase-007",
        },
        {
            "case_id": "showcase-008",
            "complaint_text": "My family account was closed and I was told a suspicious charge was made without my consent.",
            "synthetic": True,
            "source_sample_id": "showcase-008",
        },
        {
            "case_id": "showcase-009",
            "complaint_text": "My direct deposit was delayed and my employer says there was a mismatch in my account details.",
            "synthetic": True,
            "source_sample_id": "showcase-009",
        },
        {
            "case_id": "showcase-010",
            "complaint_text": "I keep getting an error when trying to sign in to my health portal and I cannot access my records.",
            "synthetic": True,
            "source_sample_id": "showcase-010",
        },
        {
            "case_id": "showcase-011",
            "complaint_text": "A retailer denied my refund because I was treated differently after I reported a discrimination issue in the branch.",
            "synthetic": True,
            "source_sample_id": "showcase-011",
        },
        {
            "case_id": "showcase-012",
            "complaint_text": "The transaction history shows a charge for a service I never used and the merchant claims it was a valid payment.",
            "synthetic": True,
            "source_sample_id": "showcase-012",
        },
    ]
    labels = [
        {"case_id": "showcase-001", "category": "cards_payments", "severity": "SEV1", "queue": "cards_payments", "label_status": "proposed"},
        {"case_id": "showcase-002", "category": "accounts", "severity": "SEV2", "queue": "accounts", "label_status": "proposed"},
        {"case_id": "showcase-003", "category": "fraud_scams", "severity": "SEV1", "queue": "fraud_scams", "label_status": "proposed"},
        {"case_id": "showcase-004", "category": "lending", "severity": "SEV2", "queue": "lending", "label_status": "proposed"},
        {"case_id": "showcase-005", "category": "service_access", "severity": "SEV3", "queue": "service_access", "label_status": "proposed"},
        {"case_id": "showcase-006", "category": "discrimination", "severity": "SEV1", "queue": "discrimination", "label_status": "proposed"},
        {"case_id": "showcase-007", "category": "fraud_scams", "severity": "SEV2", "queue": "fraud_scams", "label_status": "proposed"},
        {"case_id": "showcase-008", "category": "accounts", "severity": "SEV2", "queue": "accounts", "label_status": "proposed"},
        {"case_id": "showcase-009", "category": "accounts", "severity": "SEV3", "queue": "accounts", "label_status": "proposed"},
        {"case_id": "showcase-010", "category": "service_access", "severity": "SEV2", "queue": "service_access", "label_status": "proposed"},
        {"case_id": "showcase-011", "category": "discrimination", "severity": "SEV2", "queue": "discrimination", "label_status": "proposed"},
        {"case_id": "showcase-012", "category": "other", "severity": "SEV3", "queue": "other", "label_status": "proposed"},
    ]
    return complaints, labels


def build_baseline() -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    complaints: list[dict[str, object]] = []
    labels: list[dict[str, object]] = []
    template_rows = [
        ("cards_payments", "My card was charged twice for a cancelled subscription and I need the duplicate fee reversed immediately.", "SEV1"),
        ("accounts", "I cannot access my account after a password reset because verification never arrives and I am locked out.", "SEV2"),
        ("fraud_scams", "A scammer pretending to be support told me to send money to a new account and I need help reversing it.", "SEV1"),
        ("lending", "My loan statement shows a missed payment even though automatic payment was already processed.", "SEV2"),
        ("service_access", "I cannot access my benefits portal and my documents are not loading after sign-in.", "SEV3"),
        ("discrimination", "I was treated differently after reporting a disability accommodation request to a representative.", "SEV1"),
        ("other", "I received a charge for a service I did not authorize on my account statement.", "SEV3"),
    ]
    for idx in range(30):
        category, text, severity = template_rows[idx % len(template_rows)]
        case_id = f"baseline-{idx + 1:03d}"
        complaints.append({
            "case_id": case_id,
            "complaint_text": text,
            "synthetic": True,
            "source_sample_id": case_id,
        })
        labels.append({
            "case_id": case_id,
            "category": category,
            "severity": severity,
            "queue": category,
            "label_status": "reviewed",
        })
    return complaints, labels


def build_holdout() -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    complaint_specs = [
        ("holdout-001", "My credit card was charged twice for the same flight purchase and I need the duplicate charge removed.", "cards_payments", "SEV1"),
        ("holdout-002", "An unauthorized transfer was sent from my savings account and I cannot access the funds after the transfer.", "accounts", "SEV1"),
        ("holdout-003", "A scammer pretended to be customer support and asked me to move my money to a secure account immediately.", "fraud_scams", "SEV1"),
        ("holdout-004", "My mortgage payment posting was delayed even though the bank had already received the funds from my account.", "lending", "SEV2"),
        ("holdout-005", "My benefits portal shows a lockout after repeated password resets and I cannot access my service report.", "service_access", "SEV2"),
        ("holdout-006", "A lender declined my rental application after I requested a reasonable accommodation for my disability.", "discrimination", "SEV1"),
        ("holdout-007", "The payment history shows a duplicate debit for a subscription I cancelled last week.", "cards_payments", "SEV3"),
        ("holdout-008", "My account balance is missing funds after a card transaction I never approved.", "accounts", "SEV1"),
        ("holdout-009", "A fraudulent payment request was sent to my account and I want the transfer reversed before it clears.", "fraud_scams", "SEV1"),
        ("holdout-010", "I attempted to use my lending portal, but my payment record is missing and the site marks it as failed.", "lending", "SEV2"),
        ("holdout-011", "The customer service system marked my health records as inaccessible after a failed login and I cannot retrieve them.", "service_access", "SEV2"),
        ("holdout-012", "I was refused credit again because the branch treated me differently after I reported my disability status.", "discrimination", "SEV1"),
        ("holdout-013", "A fake invoice asked me to pay again for a service already completed and the payment looked unauthorized.", "fraud_scams", "SEV3"),
        ("holdout-014", "My payment card was debited twice for the same weekly subscription, and I need the duplicate charge removed.", "cards_payments", "SEV1"),
        ("holdout-015", "I was told my account had been locked for fraud review, and I still cannot access my online statements.", "accounts", "SEV2"),
        ("holdout-016", "My provider says a transfer was sent to an incorrect account number even though I never approved it.", "accounts", "SEV1"),
        ("holdout-017", "The app blocks access to my service account and says my password reset link is expired before I can log in.", "service_access", "SEV3"),
        ("holdout-018", "I was denied a loan because the lender treated me differently after concerns about my disability were raised.", "discrimination", "SEV1"),
        ("holdout-019", "My family account shows a money transfer I did not authorize and the funds are missing from my balance.", "accounts", "SEV1"),
        ("holdout-020", "The merchant billed me twice for the same purchase and I need the duplicate payment reversed immediately.", "cards_payments", "SEV2"),
        ("holdout-021", "I cannot sign in to my account because the reset link loops without completing authentication.", "accounts", "SEV3"),
        ("holdout-022", "A scam message told me to share my account verification code to unblock my payment authorization.", "fraud_scams", "SEV2"),
        ("holdout-023", "My payment application was denied because I was treated differently after being flagged as disabled.", "discrimination", "SEV2"),
        ("holdout-024", "The service portal shows an incorrect account balance and I still cannot access my records for the last month.", "service_access", "SEV3"),
        ("holdout-025", "A fake service request tried to charge my account again after I had already paid for the service.", "cards_payments", "SEV3"),
        ("holdout-026", "My direct deposit did not arrive and my payment history shows a mismatch in the account details.", "accounts", "SEV2"),
        ("holdout-027", "I was told a transaction was completed for a billing error I never authorized, and the funds are gone.", "accounts", "SEV1"),
        ("holdout-028", "The service contact ignored my accommodation request and refused to process my application fairly.", "service_access", "SEV3"),
        ("holdout-029", "My payment account shows a duplicate charge for the same gym renewal despite my cancellation request.", "cards_payments", "SEV3"),
        ("holdout-030", "I cannot access my account history and the app says my credentials were reset by an unknown device.", "other", "SEV2"),
    ]
    complaints = [
        {"case_id": case_id, "complaint_text": text, "synthetic": True, "source_sample_id": case_id}
        for case_id, text, _, _ in complaint_specs
    ]
    labels = [
        {"case_id": case_id, "category": category, "severity": severity, "queue": category, "label_status": "pending_review"}
        for case_id, _, category, severity in complaint_specs
    ]
    return complaints, labels


def build_drift() -> tuple[list[dict[str, object]], list[dict[str, object]], list[dict[str, object]], list[dict[str, object]]]:
    baseline_rows = [
        {"case_id": f"baseline-drift-{idx:03d}", "complaint_text": text, "synthetic": True}
        for idx, text in enumerate([
            "The service portal is failing and my account access is blocked after a password reset.",
            "I cannot view my statements because the app keeps looping during login and access is denied.",
            "The online account is locked and I cannot inspect my recent payments after repeated sign-in failures.",
            "The secure portal is down and I cannot reach my file after a password reset step failed.",
            "My login request loops and I cannot access the account page to review payment records.",
            "I keep getting bounced out of the service portal and my account history is unavailable.",
            "Password resets are broken and the app keeps locking me out of my account information.",
            "The sign-in flow is failing and I cannot reach my health records or payment dashboard.",
            "My access is blocked after repeated attempts and I cannot open the benefits portal.",
            "The portal shows an error and I cannot read my statements because the app is redirecting.",
            "My account is locked after a failed verification attempt and record access is denied.",
            "I cannot view my recent transfers because the portal keeps failing authentication.",
            "The financial portal is inaccessible and I cannot sign in due to repeated loops.",
            "The app says my customer account is inactive and I am locked from the documents page.",
            "I cannot complete login and my account access fails after the password reset workflow.",
            "The site is denying access and my records are unavailable after repeated authentication error.",
            "I am temporarily locked out of the portal and cannot access my account details.",
            "I keep seeing a login loop while attempting to access my account and service records.",
            "My access is blocked and my portal repeatedly asks me to reset my password again.",
            "The payment portal is failing and I cannot open the statements page after the reset flow.",
            "The sign-in process loops and my record page remains unavailable after authentication issues.",
            "I cannot access my account because the service portal continually redirects to the login page.",
            "The access system is failing and a reset loop prevents me from reviewing my account.",
            "My account still fails self-service access after repeated verification attempts and I cannot login.",
            "I am locked out of the portal and cannot read my account history after credential failures.",
            "The website stops at the login loop and I cannot reach my account because of access issues.",
            "The system keeps asking me to reset my password and then loops before I can see my records.",
            "I cannot use the service because the app is repeatedly failing during account sign in.",
            "My portal is unavailable and I am unable to access my data after failed authentication.",
            "The authentication flow is broken and my account page shows repeated lockout errors.",
        ])
    ]
    window_1 = [
        {"case_id": f"drift-w1-{idx:03d}", "complaint_text": text, "synthetic": True}
        for idx, text in enumerate([
            "The app is slow and service access fails when I try to view my records after a password reset.",
            "I cannot access my online payment dashboard after a login loop and my recent statements are unavailable.",
            "The mobile app blocked my account after multiple failed sign-ins and I cannot check my recent transfers.",
            "I need access to my account history, but authentication loops repeatedly and my data is unavailable.",
            "The service portal shows an error when I try to access my account and I cannot view my payment records.",
            "I cannot sign in and I am locked out from the account portal after a password reset request.",
            "My online access is blocked and I keep receiving a login loop when I try to open my statements.",
            "Repeated authentication failures locked my account and I cannot access my recent payment details.",
            "The portal refuses my login and says my account is temporarily locked while I wait for verification.",
            "After the reset flow, I cannot access my account and the portal repeatedly loops during sign in.",
        ], start=1)
    ]
    window_2 = [
        {"case_id": f"drift-w2-{idx:03d}", "complaint_text": text, "synthetic": True}
        for idx, text in enumerate([
            "A fake scammer asked me to verify my account code and transfer funds to a safe account immediately.",
            "A scam email demanded a payment to unlock my account and said my balance would be restored once transferred.",
            "My card was charged twice for a purchase I never approved and the duplicate amount is still there.",
            "I was told to move money to a new account to protect my funds after a fake fraud alert.",
            "The account team said my transfer was held while a scammer tried to get me to move funds elsewhere.",
            "I was asked to send funds to a secure account to confirm my direct-deposit details and stop a scam.",
            "My payment app shows two identical charges from the same merchant and I need the duplicate corrected.",
            "A fraudulent specialist requested I send my account verification code to reverse a fake transaction.",
            "I was asked to move money between accounts to reverse a fraudulent payment before the funds were lost.",
            "My account shows an unauthorized payment and a scammer is telling me to send my balance to another account.",
        ], start=1)
    ]
    labels_1 = [{"case_id": row["case_id"], "category": "service_access", "severity": "SEV3", "queue": "service_access"} for row in window_1]
    labels_2 = [{"case_id": row["case_id"], "category": "fraud_scams", "severity": "SEV1", "queue": "fraud_scams"} for row in window_2]
    return baseline_rows, window_1, window_2, labels_1 + labels_2


def write_manifest() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    showcase, showcase_labels = build_showcase()
    baseline, baseline_labels = build_baseline()
    holdout, holdout_labels = build_holdout()
    baseline_drift, window_1, window_2, drift_labels = build_drift()

    write_jsonl(DATA_DIR / "showcase" / "complaints.jsonl", showcase)
    write_jsonl(DATA_DIR / "showcase" / "labels.jsonl", showcase_labels)
    write_jsonl(DATA_DIR / "baseline" / "complaints.jsonl", baseline)
    write_jsonl(DATA_DIR / "baseline" / "labels.jsonl", baseline_labels)
    write_jsonl(DATA_DIR / "holdout" / "complaints.jsonl", holdout)
    write_jsonl(DATA_DIR / "holdout" / "labels.jsonl", holdout_labels)
    write_jsonl(DATA_DIR / "drift" / "baseline.jsonl", baseline_drift)
    write_jsonl(DATA_DIR / "drift" / "window_1.jsonl", window_1)
    write_jsonl(DATA_DIR / "drift" / "window_2.jsonl", window_2)
    write_jsonl(DATA_DIR / "drift" / "window_1_labels.jsonl", [
        {"case_id": row["case_id"], "category": "service_access", "severity": "SEV3", "queue": "service_access"}
        for row in window_1
    ])
    write_jsonl(DATA_DIR / "drift" / "window_2_labels.jsonl", [
        {"case_id": row["case_id"], "category": "fraud_scams", "severity": "SEV1", "queue": "fraud_scams"}
        for row in window_2
    ])

    manifest = {
        "dataset_version": "phase-c-v1",
        "synthetic": True,
        "families": {
            "showcase": {"complaints": len(showcase), "labels": len(showcase_labels)},
            "baseline": {"complaints": len(baseline), "labels": len(baseline_labels)},
            "holdout": {"complaints": len(holdout), "labels": len(holdout_labels)},
            "drift": {"baseline": len(baseline_drift), "window_1": len(window_1), "window_2": len(window_2)},
        },
        "label_status": {
            "showcase": "proposed",
            "baseline": "reviewed",
            "holdout": "pending_review",
            "drift": "synthetic_only",
        },
        "notes": [
            "All complaint records are synthetic and intentionally de-identified.",
            "Input and label streams are kept separate to prevent leakage.",
        ],
    }
    (DATA_DIR / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")


if __name__ == "__main__":
    write_manifest()
    print(f"Wrote synthetic Phase C datasets under {DATA_DIR}")
