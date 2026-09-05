"""
Contextual Hinglish Customer Messaging Module.

Uses Google Gemini LLM to generate dynamic, authentic, non-templated Hinglish
messages (Latin script) tied directly to the specific failure diagnosis and proposed recovery action.
Fails loudly if the LLM call is unsuccessful (per RecoverAI Ground Truth — zero silent canned fallbacks).
"""

import json
import logging
from decimal import Decimal
from typing import Any, Dict, Optional
import httpx

from app.core.config import settings

logger = logging.getLogger("recoverai.mandate.messaging")


def generate_contextual_hinglish_message(
    failure_code: str,
    action_type: str,
    amount: Any,
    channel: str = "WHATSAPP",
    merchant_name: str = "Subscription Service",
    customer_context: Optional[Dict[str, Any]] = None,
    allow_mock: bool = False,
) -> str:
    """
    Generates a situation-specific, conversational Hinglish message via Gemini API.

    Requirements:
    - Must be natural, culturally authentic Latin-script Hinglish.
    - Must directly reference the specific payment failure root cause.
    - Must clearly present the specific proposed recovery action / incentive.
    - NEVER a generic canned template ("Aapka payment fail ho gaya").
    - Fails loudly with RuntimeError if LLM generation fails and allow_mock is False.
    """
    clean_amount = f"₹{Decimal(str(amount)):,.2f}"

    if not settings.gemini_api_key:
        if allow_mock:
            # Explicit opt-in mock for offline CI/test environments only
            return (
                f"[MOCK_HINGLISH] Namaste! Aapka {merchant_name} payment ({clean_amount}) "
                f"{failure_code} ki wajah se hold pe hai. Humne {action_type} initiate kiya hai."
            )
        raise RuntimeError(
            "GEMINI_API_KEY is not configured. Contextual Hinglish messaging requires live LLM generation "
            "per Ground Truth rules. Silent canned template fallback is strictly prohibited."
        )

    api_key = settings.gemini_api_key
    model = settings.gemini_model or "gemini-3.5-flash-lite"
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"

    system_prompt = (
        "You are RecoverAI's Contextual Customer Communications Engine for India.\n"
        "Your task is to craft an authentic, empathetic, professional customer message in natural HINGLISH "
        "(Hindi language written entirely in the Roman/Latin alphabet).\n\n"
        "Strict Editorial Guidelines:\n"
        "1. DO NOT use generic canned phrases like 'Aapka payment fail ho gaya' or 'Kripya dubara try karein'.\n"
        "2. Directly explain the specific failure diagnosis in simple conversational terms "
        "(e.g. UPI bank server timeout vs autopay mandate revoked vs checkout abandoned).\n"
        "3. Match the proposed action:\n"
        "   - RETRY: Inform customer of automatic retry schedule and provide instant manual pay link.\n"
        "   - WHATSAPP/EMAIL: Explain issue clearly with 1-click resolution link.\n"
        "   - DISCOUNT: Highlight the incentive coupon and remaining validity.\n"
        "   - ESCALATE: Inform that support team is assisting with their high-priority account.\n"
        "4. Tone: Courteous, fintech-professional (like Razorpay/CRED/Swiggy).\n"
        "5. Keep message concise (2-4 sentences max), clear, and actionable.\n"
        "6. Return ONLY a valid JSON object with the single key 'message':\n"
        "{\n"
        '  "message": "Conversational Hinglish message here..."\n'
        "}"
    )

    user_payload = {
        "failure_code": failure_code,
        "action_type": action_type,
        "channel": channel,
        "amount": clean_amount,
        "merchant_name": merchant_name,
        "customer_context": customer_context or {},
    }

    payload = {
        "system_instruction": {"parts": [{"text": system_prompt}]},
        "contents": [{"parts": [{"text": json.dumps(user_payload)}]}],
        "generationConfig": {
            "response_mime_type": "application/json",
            "temperature": 0.3,
        },
    }

    headers = {"Content-Type": "application/json"}
    max_retries = 3
    last_err = None

    try:
        import time
        with httpx.Client(timeout=50.0) as client:
            for attempt in range(max_retries):
                try:
                    resp = client.post(url, json=payload, headers=headers)
                    if resp.status_code == 429 and attempt < max_retries - 1:
                        time.sleep(5.0)
                        continue
                    if resp.status_code != 200:
                        raise RuntimeError(f"Gemini API returned HTTP {resp.status_code}: {resp.text}")
                    data = resp.json()
                    raw_text = data["candidates"][0]["content"]["parts"][0]["text"]
                    parsed = json.loads(raw_text)
                    message = parsed.get("message")
                    if not message or not isinstance(message, str):
                        raise ValueError(f"Malformed LLM response: missing 'message' key in {raw_text}")
                    return message.strip()
                except (httpx.ReadTimeout, httpx.ConnectTimeout) as t_err:
                    last_err = t_err
                    if attempt < max_retries - 1:
                        time.sleep(3.0)
                        continue
                    raise

    except Exception as err:
        if allow_mock:
            logger.warning(f"Live LLM call failed, returning mock due to allow_mock=True: {err}")
            return (
                f"[MOCK_HINGLISH] Namaste! Aapka {merchant_name} payment ({clean_amount}) "
                f"{failure_code} ki wajah se hold pe hai. Humne {action_type} initiate kiya hai."
            )
        # Fails loudly per user requirement — zero silent canned template fallback
        raise RuntimeError(
            f"Failed to generate contextual Hinglish message via LLM: {err}. "
            "Silent fallback to canned template is prohibited by Ground Truth."
        ) from err
