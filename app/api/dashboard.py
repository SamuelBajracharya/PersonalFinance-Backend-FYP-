from datetime import datetime, timezone
from decimal import Decimal

import httpx
import pandas as pd
from dateutil.relativedelta import relativedelta
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from app import crud
from app.config.settings import settings
from app.crud.budget import update_completed_budgets_for_user
from app.crud.stock_instrument import get_stock_instruments_by_user
from app.models.bank import BankAccount
from app.models.user import User
from app.schemas.dashboard import (
    AISuggestionItem,
    BudgetGoalItem,
    DashboardAISuggestionsResponse,
    DashboardResponse,
    ExpenseCategoryChartItem,
    LineSeries,
    LineSeriesDataPoint,
    RecentTransactionItem,
    StockItem,
    SummaryData,
)
from app.services.reward_evaluation import evaluate_rewards
from app.services.budget_goal_intelligence import get_all_budget_goal_statuses
from app.utils.deps import get_current_user, get_db

router = APIRouter()


def _get_user_nabil_account(db: Session, user_id: str) -> BankAccount:
    account = (
        db.query(BankAccount)
        .filter(
            BankAccount.user_id == user_id,
            BankAccount.is_active == True,
            func.lower(BankAccount.bank_name).like("%nabil%"),
        )
        .first()
    )
    if not account:
        raise HTTPException(
            status_code=404,
            detail="No active Nabil bank account found for user",
        )
    return account


def _to_decimal_str(value: float | Decimal) -> str:
    return f"{Decimal(str(value)):.2f}"


def _build_fallback_suggestions(
    top_expense_categories: list[tuple[str, float]],
) -> list[AISuggestionItem]:
    suggestions: list[AISuggestionItem] = []
    for category, amount in top_expense_categories:
        text = (
            f"Your spending on {category} is high (Rs. {amount:.2f}). "
            "Set a weekly cap and cut at least 10% from non-essential purchases in this category."
        )
        suggestions.append(AISuggestionItem(category=category, suggestion=text))
    return suggestions


async def _generate_ai_suggestions(
    top_expense_categories: list[tuple[str, float]],
) -> list[AISuggestionItem]:
    if not top_expense_categories:
        return []

    category_lines = "\n".join(
        [
            f"- {category}: Rs. {amount:.2f}"
            for category, amount in top_expense_categories
        ]
    )

    prompt = (
        "You are a financial coach.\n"
        "Create exactly 3 concise spending suggestions based only on these top expense categories.\n"
        "Return exactly 3 lines in this format: <category>|<suggestion>.\n"
        "No numbering. No extra text.\n\n"
        "Top expense categories:\n"
        f"{category_lines}"
    )

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(
                settings.OLLAMA_API_URL,
                json={
                    "model": "phi3:mini",
                    "prompt": prompt,
                    "stream": False,
                },
            )
            response.raise_for_status()

        raw_output = response.json().get("response", "")
        parsed: list[AISuggestionItem] = []
        valid_categories = {
            category.lower(): category for category, _ in top_expense_categories
        }

        for line in raw_output.splitlines():
            if "|" not in line:
                continue
            category_part, suggestion_part = line.split("|", 1)
            category = category_part.strip()
            suggestion = suggestion_part.strip()
            if not category or not suggestion:
                continue

            normalized = category.lower()
            if normalized in valid_categories:
                category = valid_categories[normalized]

            parsed.append(AISuggestionItem(category=category, suggestion=suggestion))

        if len(parsed) >= 3:
            return parsed[:3]
    except Exception:
        pass

    return _build_fallback_suggestions(top_expense_categories)


def _format_line_series_data(groups, prefix: str) -> list[LineSeries]:
    income_points: list[LineSeriesDataPoint] = []
    expense_points: list[LineSeriesDataPoint] = []

    for label, group in groups:
        income = group[group["type"] == "CREDIT"]["amount"].sum()
        expense = group[group["type"] == "DEBIT"]["amount"].sum()

        income_points.append(LineSeriesDataPoint(x=str(label), y=f"{income:.2f}"))
        expense_points.append(LineSeriesDataPoint(x=str(label), y=f"{expense:.2f}"))

    return [
        LineSeries(id=f"{prefix}_income", data=income_points),
        LineSeries(id=f"{prefix}_expense", data=expense_points),
    ]


def _month_window(now: datetime) -> tuple[pd.Timestamp, pd.Timestamp]:
    month_end = pd.Timestamp(now)
    # Use a fixed 4-week horizon for monthly dashboard calculations.
    month_start = (month_end - pd.Timedelta(days=27)).replace(
        hour=0,
        minute=0,
        second=0,
        microsecond=0,
    )
    return month_start, month_end


def _year_window(now: datetime) -> tuple[pd.Timestamp, pd.Timestamp]:
    year_end = pd.Timestamp(now)
    year_start = (year_end - relativedelta(years=1)).replace(
        hour=0,
        minute=0,
        second=0,
        microsecond=0,
    )
    return year_start, year_end


def _build_monthly_line_series(
    df_month: pd.DataFrame, month_start: pd.Timestamp, month_end: pd.Timestamp
) -> list[LineSeries]:
    week_labels = ["Week 1", "Week 2", "Week 3", "Week 4"]

    if df_month.empty:
        income_points = [
            LineSeriesDataPoint(x=label, y="0.00") for label in week_labels
        ]
        expense_points = [
            LineSeriesDataPoint(x=label, y="0.00") for label in week_labels
        ]
        return [
            LineSeries(id="monthly_income", data=income_points),
            LineSeries(id="monthly_expense", data=expense_points),
        ]

    df_month = df_month.copy()
    start_day = month_start.normalize()
    day_delta = (df_month["date"].dt.normalize() - start_day).dt.days
    # Fixed 28-day window split into four 7-day buckets.
    df_month["week_index"] = (day_delta // 7) + 1
    df_month["week_index"] = df_month["week_index"].clip(lower=1, upper=4)

    monthly_income = (
        df_month[df_month["type"] == "CREDIT"]
        .groupby("week_index")["amount"]
        .sum()
        .reindex([1, 2, 3, 4], fill_value=0)
    )
    monthly_expenses = (
        df_month[df_month["type"] == "DEBIT"]
        .groupby("week_index")["amount"]
        .sum()
        .reindex([1, 2, 3, 4], fill_value=0)
    )

    income_points = [
        LineSeriesDataPoint(x=week_labels[i - 1], y=f"{value:.2f}")
        for i, value in monthly_income.items()
    ]
    expense_points = [
        LineSeriesDataPoint(x=week_labels[i - 1], y=f"{value:.2f}")
        for i, value in monthly_expenses.items()
    ]

    return [
        LineSeries(id="monthly_income", data=income_points),
        LineSeries(id="monthly_expense", data=expense_points),
    ]


def _build_yearly_line_series(
    df_year: pd.DataFrame, year_start: pd.Timestamp, year_end: pd.Timestamp
) -> list[LineSeries]:
    month_range = pd.date_range(
        start=year_start.normalize(), end=year_end.normalize(), freq="MS"
    ).to_period("M")

    if df_year.empty:
        income_points = [
            LineSeriesDataPoint(x=period.strftime("%b %Y"), y="0.00")
            for period in month_range
        ]
        expense_points = [
            LineSeriesDataPoint(x=period.strftime("%b %Y"), y="0.00")
            for period in month_range
        ]
        return [
            LineSeries(id="yearly_income", data=income_points),
            LineSeries(id="yearly_expense", data=expense_points),
        ]

    df_year = df_year.copy()
    df_year["month_year"] = df_year["date"].dt.to_period("M")

    yearly_income = (
        df_year[df_year["type"] == "CREDIT"]
        .groupby("month_year")["amount"]
        .sum()
        .reindex(month_range, fill_value=0)
    )
    yearly_expenses = (
        df_year[df_year["type"] == "DEBIT"]
        .groupby("month_year")["amount"]
        .sum()
        .reindex(month_range, fill_value=0)
    )

    income_points = [
        LineSeriesDataPoint(x=str(period.strftime("%b %Y")), y=f"{value:.2f}")
        for period, value in yearly_income.items()
    ]
    expense_points = [
        LineSeriesDataPoint(x=str(period.strftime("%b %Y")), y=f"{value:.2f}")
        for period, value in yearly_expenses.items()
    ]

    return [
        LineSeries(id="yearly_income", data=income_points),
        LineSeries(id="yearly_expense", data=expense_points),
    ]


def _build_expense_category_chart(
    df_window: pd.DataFrame,
) -> list[ExpenseCategoryChartItem]:
    if df_window.empty:
        return []

    top_expense_series = (
        df_window[df_window["type"] == "DEBIT"]
        .groupby("category")["amount"]
        .sum()
        .sort_values(ascending=False)
    )

    return [
        ExpenseCategoryChartItem(
            id=category if category else "Uncategorized",
            label=category if category else "Uncategorized",
            value=f"{amount:.2f}",
        )
        for category, amount in top_expense_series.head(5).items()
    ]


def _top_budget_goals(db: Session, user_id: str) -> list[BudgetGoalItem]:
    statuses = get_all_budget_goal_statuses(db, user_id)
    ranked: list[tuple[float, BudgetGoalItem]] = []

    for status_payload in statuses:
        budget_amount = float(status_payload.get("budget_amount") or 0)
        spent = float(status_payload.get("current_spend") or 0)
        remaining = float(status_payload.get("remaining_budget") or 0)
        usage_pct = float(status_payload.get("progress_percent") or 0)
        predicted_to_exceed = bool(status_payload.get("predicted_to_exceed"))

        if usage_pct >= 100:
            status = "Overspent"
        elif predicted_to_exceed:
            status = "At Risk"
        elif usage_pct >= 80:
            status = "Warning"
        else:
            status = "On Track"

        ranked.append(
            (
                usage_pct,
                BudgetGoalItem(
                    id=str(status_payload.get("budget_id")),
                    category=str(status_payload.get("category") or "Uncategorized"),
                    budgetAmount=f"{budget_amount:.2f}",
                    spentAmount=f"{spent:.2f}",
                    remainingBudget=f"{remaining:.2f}",
                    usagePct=f"{usage_pct:.2f}",
                    status=status,
                ),
            )
        )

    ranked.sort(key=lambda item: item[0], reverse=True)
    return [item[1] for item in ranked[:3]]


def _top_stocks(db: Session, user_id: str) -> list[StockItem]:
    stocks = get_stock_instruments_by_user(db, user_id)
    ranked: list[tuple[float, StockItem]] = []

    for stock in stocks:
        quantity = float(stock.quantity or 0)
        current_price = (
            float(stock.current_price or 0) if stock.current_price is not None else None
        )
        average_buy_price = (
            float(stock.average_buy_price or 0)
            if stock.average_buy_price is not None
            else None
        )
        market_value = quantity * current_price if current_price is not None else 0.0

        ranked.append(
            (
                market_value,
                StockItem(
                    id=str(stock.id),
                    symbol=stock.symbol,
                    name=stock.name,
                    quantity=f"{quantity:.6f}",
                    currentPrice=(
                        f"{current_price:.6f}" if current_price is not None else None
                    ),
                    averageBuyPrice=(
                        f"{average_buy_price:.6f}"
                        if average_buy_price is not None
                        else None
                    ),
                    marketValue=(
                        f"{market_value:.2f}" if current_price is not None else None
                    ),
                ),
            )
        )

    ranked.sort(key=lambda item: item[0], reverse=True)
    return [item[1] for item in ranked[:2]]


def _recent_transactions(transactions) -> list[RecentTransactionItem]:
    sorted_transactions = sorted(
        transactions,
        key=lambda t: t.date or datetime.min.replace(tzinfo=timezone.utc),
        reverse=True,
    )

    result: list[RecentTransactionItem] = []
    for tx in sorted_transactions[:6]:
        result.append(
            RecentTransactionItem(
                id=str(tx.id),
                date=tx.date.isoformat() if tx.date else "",
                type=tx.type,
                amount=_to_decimal_str(tx.amount or 0),
                category=tx.category,
                description=tx.description,
                merchant=tx.merchant,
            )
        )
    return result


def _in_window(value: datetime | None, start: pd.Timestamp, end: pd.Timestamp) -> bool:
    if value is None:
        return False
    ts = pd.to_datetime(value, utc=True)
    return start <= ts <= end


@router.get("/", response_model=DashboardResponse)
async def get_dashboard_data(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    db_bank_account = _get_user_nabil_account(db, current_user.user_id)
    external_id = db_bank_account.external_account_id

    # Update completed budgets and evaluate rewards
    update_completed_budgets_for_user(db=db, user_id=current_user.user_id)
    evaluate_rewards(db=db, user=current_user)

    transactions = crud.get_transactions_by_account(
        db=db, account_id=db_bank_account.id
    )

    if not transactions:
        empty_series = LineSeries(id="", data=[])
        return DashboardResponse(
            summary=SummaryData(
                totalIncome="0.00",
                totalExpenses="0.00",
                totalBalance="0.00",
                savingRate="0.00",
            ),
            yearlyLineSeries=[empty_series, empty_series],
            monthlyLineSeries=[empty_series, empty_series],
            recentTransactions=[],
            topBudgetGoals=_top_budget_goals(db, current_user.user_id),
            topStocks=_top_stocks(db, current_user.user_id),
            aiSuggestions=[],
            monthlyExpenseCategoryChart=[],
            yearlyExpenseCategoryChart=[],
        )

    df = pd.DataFrame(
        [
            {
                "amount": float(t.amount),
                "type": t.type,
                "date": t.date,
                "category": t.category,
            }
            for t in transactions
        ]
    )

    df["date"] = pd.to_datetime(df["date"], utc=True)
    df["amount"] = df["amount"].astype(float)

    now = datetime.now(timezone.utc)
    month_start, month_end = _month_window(now)
    year_start, year_end = _year_window(now)

    df_month = df[(df["date"] >= month_start) & (df["date"] <= month_end)].copy()
    df_year = df[(df["date"] >= year_start) & (df["date"] <= year_end)].copy()

    total_income = df_month[df_month["type"] == "CREDIT"]["amount"].sum()
    total_expenses = df_month[df_month["type"] == "DEBIT"]["amount"].sum()
    total_balance = total_income - total_expenses
    saving_rate = ((total_balance / total_income) * 100) if total_income > 0 else 0.0

    summary_data = SummaryData(
        totalIncome=f"{total_income:.2f}",
        totalExpenses=f"{total_expenses:.2f}",
        totalBalance=f"{total_balance:.2f}",
        savingRate=f"{saving_rate:.2f}",
    )

    yearly_line_series = _build_yearly_line_series(df_year, year_start, year_end)
    monthly_line_series = _build_monthly_line_series(df_month, month_start, month_end)

    top_expense_series = (
        df_month[df_month["type"] == "DEBIT"]
        .groupby("category")["amount"]
        .sum()
        .sort_values(ascending=False)
    )

    top_expense_categories = [
        (category if category else "Uncategorized", float(amount))
        for category, amount in top_expense_series.head(3).items()
    ]

    ai_suggestions = await _generate_ai_suggestions(top_expense_categories)
    monthly_expense_category_chart = _build_expense_category_chart(df_month)
    yearly_expense_category_chart = _build_expense_category_chart(df_year)

    return DashboardResponse(
        summary=summary_data,
        yearlyLineSeries=yearly_line_series,
        monthlyLineSeries=monthly_line_series,
        recentTransactions=_recent_transactions(
            [tx for tx in transactions if _in_window(tx.date, month_start, month_end)]
        ),
        topBudgetGoals=_top_budget_goals(db, current_user.user_id),
        topStocks=_top_stocks(db, current_user.user_id),
        aiSuggestions=ai_suggestions,
        monthlyExpenseCategoryChart=monthly_expense_category_chart,
        yearlyExpenseCategoryChart=yearly_expense_category_chart,
    )


@router.get("/ai-suggestions", response_model=DashboardAISuggestionsResponse)
async def get_dashboard_ai_suggestions(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    db_bank_account = _get_user_nabil_account(db, current_user.user_id)
    external_id = db_bank_account.external_account_id

    transactions = crud.get_transactions_by_account(
        db=db, account_id=db_bank_account.id
    )
    if not transactions:
        return DashboardAISuggestionsResponse(suggestions=[])

    df = pd.DataFrame(
        [
            {
                "amount": float(t.amount),
                "type": t.type,
                "category": t.category,
                "date": t.date,
            }
            for t in transactions
        ]
    )

    df["date"] = pd.to_datetime(df["date"], utc=True)

    now = datetime.now(timezone.utc)
    month_start, month_end = _month_window(now)
    df_month = df[(df["date"] >= month_start) & (df["date"] <= month_end)].copy()

    top_expense_series = (
        df_month[df_month["type"] == "DEBIT"]
        .groupby("category")["amount"]
        .sum()
        .sort_values(ascending=False)
    )

    top_expense_categories = [
        (category if category else "Uncategorized", float(amount))
        for category, amount in top_expense_series.head(3).items()
    ]

    suggestions = await _generate_ai_suggestions(top_expense_categories)
    return DashboardAISuggestionsResponse(suggestions=suggestions)
