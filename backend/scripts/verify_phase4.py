#!/usr/bin/env python3
"""
Phase 4 Verification Script — Diagnosis Engine (Deterministic + LLM)

Usage:
    docker compose exec backend python scripts/verify_phase4.py [--mock]
"""

import argparse
import os
import random
import sys

# Add project root to sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.config import settings
from app.engines.diagnosis import DETERMINISTIC_TAXONOMY_DIAGNOSES, diagnose_failure
from app.models.tables import DiagnosisSource

# Ambiguous raw error texts that do NOT match the 27 taxonomy codes
AMBIGUOUS_RAW_ERRORS = [
    "ERR_504_GATEWAY_TIMEOUT: Aggregator socket connection reset by peer",
    "Switch response 05: Do Not Honor from card association clearing house",
    "Network packet drop on bank reverse proxy while awaiting ACK",
    "Host system unavailable: ERR_HOST_DOWN during authorization handshake",
    "Risk engine rejection: Velocity anomaly flagged by third-party fraud filter",
    "ISO8583 parsing error: Field 48 malformed private data buffer",
    "ERR_UNEXPECTED_PSP_STATE: Session invalidated mid-transaction",
    "Internal bank core switch dropped request before debit confirmation",
    "Payment gateway returned HTTP 502 with empty body",
    "Token vault decryption failure during 3DS enrollment verification",
    "Dormant account status triggered automated bank block code 91",
    "Payment processing aborted: Merchant terminal parameters mismatched",
    "Aggregator routing failure: No active route found for bin 431581",
    "Declined: [UNKNOWN_REASON] Issuer sent non-standard response byte",
    "Customer session terminated by upstream network proxy before redirect",
]


def run_batch_verification(allow_mock: bool = False):
    print("\n" + "=" * 65)
    print("PHASE 4: DIAGNOSIS ENGINE BATCH VERIFICATION (100 MIXED EVENTS)")
    print("=" * 65)

    if not settings.gemini_api_key and not allow_mock:
        print("\n[ERROR] GEMINI_API_KEY is not configured in .env or environment!")
        print("Per Phase 4 spec, ambiguous failure cases require an LLM call.")
        print("Please set GEMINI_API_KEY in .env before running verification.")
        print("If you intentionally want to test with mock mode, pass the --mock flag.")
        sys.exit(1)

    rng = random.Random(42)
    taxonomy_codes = list(DETERMINISTIC_TAXONOMY_DIAGNOSES.keys())

    # Construct batch of 100 events: 85 clear taxonomy codes + 15 ambiguous raw errors
    batch = []
    # 85 clear taxonomy events
    for i in range(85):
        code = taxonomy_codes[i % len(taxonomy_codes)]
        batch.append({
            "id": f"evt_clear_{i:03d}",
            "error_input": code,
            "expected_ambiguous": False,
        })

    # 15 ambiguous events
    for j, err in enumerate(AMBIGUOUS_RAW_ERRORS):
        batch.append({
            "id": f"evt_ambiguous_{j:03d}",
            "error_input": err,
            "expected_ambiguous": True,
        })

    # Shuffle to simulate mixed real-world incoming stream
    rng.shuffle(batch)

    print(f"Total events in batch: {len(batch)}")
    print(f"Clear taxonomy events (deterministic): 85")
    print(f"Ambiguous raw error events (LLM):       15")
    print("\nExecuting diagnosis pipeline...")

    deterministic_results = []
    llm_results = []

    for item in batch:
        if item["expected_ambiguous"]:
            import time
            time.sleep(1.5)

        result = diagnose_failure(
            failure_code_or_text=item["error_input"],
            context={"event_id": item["id"]},
            allow_mock=allow_mock,
        )

        # Assert contract invariants
        assert result.source in (DiagnosisSource.DETERMINISTIC, DiagnosisSource.LLM), (
            f"Invalid source: {result.source}"
        )
        assert 0.0 <= result.confidence <= 1.0, f"Confidence out of bounds: {result.confidence}"
        assert isinstance(result.reason_codes, list) and len(result.reason_codes) > 0, (
            f"Reason codes must be non-empty list: {result.reason_codes}"
        )

        if result.source == DiagnosisSource.DETERMINISTIC:
            assert not item["expected_ambiguous"], (
                f"Expected ambiguous for {item['error_input']} but got deterministic"
            )
            deterministic_results.append((item, result))
        else:
            assert item["expected_ambiguous"], (
                f"Expected deterministic for {item['error_input']} but got LLM"
            )
            llm_results.append((item, result))

    # Verification Report
    print("\n" + "=" * 65)
    print("VERIFICATION REPORT — SUMMARY")
    print("=" * 65)
    print(f"Total events processed:        {len(batch)}")
    print(f"Diagnosed DETERMINISTICALLY:   {len(deterministic_results)} / 100 ({len(deterministic_results)}%) [0 LLM calls]")
    print(f"Diagnosed via LLM:             {len(llm_results)} / 100 ({len(llm_results)}%)")

    # Show 2 deterministic examples
    print("\n" + "-" * 65)
    print("EXAMPLE 1 (Deterministic Diagnosis):")
    print("-" * 65)
    ex_det1_item, ex_det1_res = deterministic_results[0]
    print(f"  Input Failure Code: {ex_det1_item['error_input']}")
    print(f"  Source:             {ex_det1_res.source.value}")
    print(f"  Confidence:         {ex_det1_res.confidence}")
    print(f"  Reason Codes:       {ex_det1_res.reason_codes}")
    print(f"  Description:        {ex_det1_res.description}")

    print("\n" + "-" * 65)
    print("EXAMPLE 2 (Deterministic Diagnosis):")
    print("-" * 65)
    ex_det2_item, ex_det2_res = deterministic_results[1]
    print(f"  Input Failure Code: {ex_det2_item['error_input']}")
    print(f"  Source:             {ex_det2_res.source.value}")
    print(f"  Confidence:         {ex_det2_res.confidence}")
    print(f"  Reason Codes:       {ex_det2_res.reason_codes}")
    print(f"  Description:        {ex_det2_res.description}")

    # Show 2 LLM examples
    print("\n" + "-" * 65)
    print("EXAMPLE 3 (LLM Diagnosis — Ambiguous Error):")
    print("-" * 65)
    ex_llm1_item, ex_llm1_res = llm_results[0]
    print(f"  Raw Error Input:    {ex_llm1_item['error_input']}")
    print(f"  Diagnosed Code:     {ex_llm1_res.failure_code}")
    print(f"  Source:             {ex_llm1_res.source.value}")
    print(f"  Confidence:         {ex_llm1_res.confidence}")
    print(f"  Reason Codes:       {ex_llm1_res.reason_codes}")
    print(f"  Description:        {ex_llm1_res.description}")

    print("\n" + "-" * 65)
    print("EXAMPLE 4 (LLM Diagnosis — Ambiguous Error):")
    print("-" * 65)
    ex_llm2_item, ex_llm2_res = llm_results[1]
    print(f"  Raw Error Input:    {ex_llm2_item['error_input']}")
    print(f"  Diagnosed Code:     {ex_llm2_res.failure_code}")
    print(f"  Source:             {ex_llm2_res.source.value}")
    print(f"  Confidence:         {ex_llm2_res.confidence}")
    print(f"  Reason Codes:       {ex_llm2_res.reason_codes}")
    print(f"  Description:        {ex_llm2_res.description}")

    print("\n" + "=" * 65)
    print("PHASE 4 VERIFICATION COMPLETE: ALL CHECKS PASSED!")
    print("=" * 65)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Phase 4 Diagnosis Verification")
    parser.add_argument(
        "--mock",
        action="store_true",
        help="Explicit opt-in to mock LLM mode (never active during final verification)",
    )
    args = parser.parse_args()
    run_batch_verification(allow_mock=args.mock)
