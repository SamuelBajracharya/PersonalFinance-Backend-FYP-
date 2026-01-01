import httpx
from sqlalchemy.orm import Session
from app.crud.bank import get_user_transactions_last_7_days
from app.schemas.ai_advisor import AIAdvisorResponse
from app.config.settings import settings


async def generate_advice(
    db: Session, user_id: str, user_prompt: str
) -> AIAdvisorResponse:
    """
    Generates financial advice using Ollama based on the user's transactions
    from the last 7 days.
    """
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
                if t.category in spending_highlights:
                    spending_highlights[t.category] += t.amount
                else:
                    spending_highlights[t.category] = t.amount

        overview = (
            f"Total Income: ${total_income:.2f}\n"
            f"Total Expenses: ${total_expenses:.2f}\n"
            f"Savings Delta: ${savings_delta:.2f}\n"
            f"Spending Highlights (by category):\n"
        )
        # Sort highlights by amount, descending
        sorted_highlights = sorted(
            spending_highlights.items(), key=lambda item: item[1], reverse=True
        )
        for category, amount in sorted_highlights:
            overview += f"- {category}: ${amount:.2f}\n"

    system_prompt = (
        "You are a friendly and encouraging financial coach. Your goal is to provide simple, actionable, and easy-to-understand financial advice. "
        "Do not use complex jargon. Always address the user directly using 'you' and 'your'.\n\n"
        "Based on the user's financial overview and their question, please do the following:\n\n"
        "1. **Rephrase the User's Question:** Restate their question to be more specific from your perspective as their advisor. Start this section with 'A better way to frame your question might be:'.\n\n"
        "2. **Provide Financial Insight:** Give 3 to 5 concise, friendly, and practical bullet points as advice. Start this section with 'Here are a few friendly suggestions:'.\n\n"
        "---BEGIN DATA---\n"
        "User's financial overview (last 7 days):\n"
        f"{overview}\n"
        "Original User Question:\n"
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

    # For now, we'll still return the raw output, but the prompt is structured
    # to make it much cleaner and more user-friendly.
    advice = raw_model_output
    summary = overview

    return AIAdvisorResponse(
        summary=summary, advice=advice, raw_model_output=raw_model_output
    )
