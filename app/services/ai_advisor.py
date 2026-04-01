import httpx
import re
from sqlalchemy.orm import Session
from app.crud.bank import get_user_transactions_last_30_days

from app.schemas.ai_advisor import AIAdvisorResponse
from app.config.settings import settings
from app.services.event_logger import log_event_async


GREETING_PHRASES = {
    "hi",
    "hello",
    "hey",
    "yo",
    "good morning",
    "good afternoon",
    "good evening",
    "namaste",
    "namaskar",
}

QUESTION_HINT_WORDS = {
    "how",
    "what",
    "why",
    "when",
    "where",
    "which",
    "should",
    "can",
    "could",
    "help",
    "save",
    "saving",
    "spend",
    "spending",
    "budget",
    "budgeting",
    "money",
    "expense",
    "expenses",
    "income",
    "invest",
    "investment",
    "loan",
    "debt",
}

GREETING_FILLER_WORDS = {
    "hi",
    "hello",
    "hey",
    "yo",
    "good",
    "morning",
    "afternoon",
    "evening",
    "there",
    "bro",
    "sir",
    "madam",
    "maam",
    "namaste",
    "namaskar",
}

PROFANITY_WORDS = {
    "fuck",
    "fucking",
    "shit",
    "bitch",
    "asshole",
    "muji",
    "mugi",
    "machikne",
    "randi",
    "lado",
}


def _extract_words(text: str) -> list[str]:
    return re.findall(r"[a-zA-Z']+", text.lower())


def _normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", text.lower().strip(" .,!?:;\t\n")).strip()


def is_greeting_only(text: str) -> bool:
    normalized = _normalize_text(text)
    if not normalized:
        return False

    if normalized in GREETING_PHRASES:
        return True

    words = _extract_words(normalized)
    if not words:
        return False

    return all(word in GREETING_FILLER_WORDS for word in words)


def is_abusive_only(text: str) -> bool:
    words = _extract_words(text)
    if not words:
        return False

    non_abusive_words = [word for word in words if word not in PROFANITY_WORDS]
    return len(non_abusive_words) == 0


def sanitize_user_prompt(text: str) -> str:
    words = _extract_words(text)
    clean_words = [word for word in words if word not in PROFANITY_WORDS]
    return " ".join(clean_words).strip()


def extract_effective_user_query(text: str) -> str:
    normalized = _normalize_text(text)
    if not normalized:
        return ""

    for phrase in sorted(GREETING_PHRASES, key=len, reverse=True):
        if normalized.startswith(f"{phrase} "):
            normalized = normalized[len(phrase) :].strip(" ,.!?;:-")
            break

    words = _extract_words(normalized)
    filtered_words = [word for word in words if word not in PROFANITY_WORDS]
    return " ".join(filtered_words).strip()


def has_question_intent(text: str) -> bool:
    lower_text = text.lower()
    if "?" in lower_text:
        return True

    words = set(_extract_words(lower_text))
    if not words:
        return False

    return len(words.intersection(QUESTION_HINT_WORDS)) > 0


async def generate_advice(
    db: Session, user_id: str, user_prompt: str
) -> AIAdvisorResponse:

    effective_prompt = extract_effective_user_query(user_prompt)

    if is_greeting_only(user_prompt):
        greeting_reply = "Hello! I can help with budgeting, saving, and spending questions whenever you're ready."

        log_event_async(
            None,
            user_id,
            "advice_generated",
            "ai_advice",
            user_id,
            {
                "user_prompt": user_prompt,
                "summary": "Greeting-only message. No financial context used.",
                "advice": greeting_reply,
            },
        )

        return AIAdvisorResponse(
            summary="Greeting-only message. No financial context used.",
            advice=greeting_reply,
            raw_model_output=greeting_reply,
        )

    if is_abusive_only(user_prompt):
        boundary_reply = (
            "I can help with your money questions, but please use respectful language."
        )

        log_event_async(
            None,
            user_id,
            "advice_generated",
            "ai_advice",
            user_id,
            {
                "user_prompt": user_prompt,
                "summary": "Abusive-only message. No financial context used.",
                "advice": boundary_reply,
            },
        )

        return AIAdvisorResponse(
            summary="Abusive-only message. No financial context used.",
            advice=boundary_reply,
            raw_model_output=boundary_reply,
        )

    if not effective_prompt or not has_question_intent(effective_prompt):
        follow_up_reply = "I can help with saving, budgeting, and spending plans. Tell me your exact money goal or question."

        log_event_async(
            None,
            user_id,
            "advice_generated",
            "ai_advice",
            user_id,
            {
                "user_prompt": user_prompt,
                "summary": "No actionable financial question detected.",
                "advice": follow_up_reply,
            },
        )

        return AIAdvisorResponse(
            summary="No actionable financial question detected.",
            advice=follow_up_reply,
            raw_model_output=follow_up_reply,
        )

    transactions = get_user_transactions_last_30_days(db, user_id)

    if not transactions:
        overview = "No transactions found for the last 30 days."
    else:
        total_income = sum(t.amount for t in transactions if t.type == "CREDIT")
        total_expenses = sum(t.amount for t in transactions if t.type == "DEBIT")
        savings_delta = total_income - total_expenses

        spending_highlights = {}
        for t in transactions:
            if t.type == "DEBIT" and t.category:
                spending_highlights[t.category] = (
                    spending_highlights.get(t.category, 0) + t.amount
                )

        overview = (
            f"Total Income: NRs.{total_income:.2f}\n"
            f"Total Expenses: NRs.{total_expenses:.2f}\n"
            f"Savings Delta: NRs.{savings_delta:.2f}\n"
            f"Spending Highlights (by category):\n"
        )

        for category, amount in sorted(
            spending_highlights.items(), key=lambda x: x[1], reverse=True
        ):
            overview += f"- {category}: NRs.{amount:.2f}\n"

    system_prompt = (
        "You are a supportive financial coach.\n"
        "Use the financial overview only as context.\n"
        "If a message contains a greeting plus a money question, answer the money question.\n"
        "Treat casual greetings and profanity as conversational noise unless they are the full message.\n"
        "Never interpret profanity/slang as product, brand, or merchant intent.\n"
        "Give direct, practical advice based on:\n"
        "- the spending trends\n"
        "- the user's question\n\n"
        "STRICT OUTPUT FORMAT RULES:\n"
        "Return your answer in a clean structured layout.\n"
        "Follow this exact format:\n\n"
        "1) <Short Heading>\n"
        "• bullet point\n"
        "• bullet point\n"
        "• bullet point\n\n"
        "---\n\n"
        "2) <Short Heading>\n"
        "• bullet point\n"
        "• bullet point\n\n"
        "---\n\n"
        "3) <Short Heading>\n"
        "• bullet point\n"
        "• bullet point\n\n"
        "Formatting rules:\n"
        "- Keep bullets short and readable\n"
        "- Each bullet must be on a new line\n"
        "- Put a line separator `---` between sections\n"
        "- Do NOT return long paragraphs\n"
        "- Do NOT reframe the user's question\n"
        "- Do NOT repeat the financial overview text\n\n"
        "---BEGIN DATA---\n"
        "Financial overview (30 days):\n"
        f"{overview}\n\n"
        "User question:\n"
        f"{effective_prompt}\n"
        "---END DATA---"
    )

    async with httpx.AsyncClient() as client:
        response = await client.post(
            settings.OLLAMA_API_URL,
            json={
                "model": "phi3:mini",
                "prompt": system_prompt,
                "stream": False,
            },
            timeout=60,
        )
        response.raise_for_status()

    raw_model_output = response.json().get("response", "")

    # preserve spacing for UI rendering
    formatted_output = raw_model_output.strip()

    # Log the advice event (non-blocking)
    log_event_async(
        None,
        user_id,
        "advice_generated",
        "ai_advice",
        user_id,  # or a generated advice id if available
        {
            "user_prompt": user_prompt,
            "summary": overview,
            "advice": formatted_output,
        },
    )
    return AIAdvisorResponse(
        summary=overview,
        advice=formatted_output,
        raw_model_output=raw_model_output,
    )
