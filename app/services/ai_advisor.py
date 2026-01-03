import httpx
from sqlalchemy.orm import Session
from app.crud.bank import get_user_transactions_last_7_days
from app.schemas.ai_advisor import AIAdvisorResponse
from app.config.settings import settings


def is_greeting(text: str) -> bool:
    greetings = [
        "hi",
        "hello",
        "hey",
        "yo",
        "good morning",
        "good afternoon",
        "good evening",
    ]
    t = text.lower().strip()
    return any(t.startswith(g) for g in greetings)


async def generate_advice(
    db: Session, user_id: str, user_prompt: str
) -> AIAdvisorResponse:

    transactions = get_user_transactions_last_7_days(db, user_id)

    if not transactions:
        overview = "No transactions found for the last 7 days."
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
            f"Total Income: ${total_income:.2f}\n"
            f"Total Expenses: ${total_expenses:.2f}\n"
            f"Savings Delta: ${savings_delta:.2f}\n"
            f"Spending Highlights (by category):\n"
        )

        for category, amount in sorted(
            spending_highlights.items(), key=lambda x: x[1], reverse=True
        ):
            overview += f"- {category}: ${amount:.2f}\n"

    # -------------------------------
    # GREETING MODE
    # -------------------------------
    if is_greeting(user_prompt):
        system_prompt = (
            "You are a friendly financial assistant.\n"
            "If the user is greeting you, reply with:\n\n"
            "1) A short warm greeting\n"
            "2) A single sentence letting them know you can help with financial questions\n\n"
            "Do NOT provide financial advice in greeting replies.\n"
            "Do NOT mention numbers or transactions.\n"
            "Keep it simple and supportive.\n\n"
            f"User message:\n{user_prompt}"
        )

    # -------------------------------
    # ADVICE MODE (STRUCTURED OUTPUT)
    # -------------------------------
    else:
        system_prompt = (
            "You are a supportive financial coach.\n"
            "Use the financial overview only as context.\n"
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
            "Financial overview (7 days):\n"
            f"{overview}\n\n"
            "User question:\n"
            f"{user_prompt}\n"
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

    return AIAdvisorResponse(
        summary=overview,
        advice=formatted_output,
        raw_model_output=raw_model_output,
    )
