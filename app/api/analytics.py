from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
import pandas as pd
from datetime import datetime
import calendar
from decimal import Decimal  

from app import crud, schemas
from app.utils.deps import get_db, get_current_user
from app.models.user import User
from app.models.bank import BankAccount

router = APIRouter()


@router.get("/{external_id}", response_model=schemas.AnalyticsResponse)
def get_financial_analytics(
    external_id: str,  # Now string for external_account_id
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # Verify account ownership using external_account_id
    db_bank_account = (
        db.query(BankAccount)
        .filter(BankAccount.external_account_id == external_id)
        .first()
    )

    if not db_bank_account or db_bank_account.user_id != current_user.user_id:
        raise HTTPException(
            status_code=404, detail="Bank account not found or not owned by user"
        )

    # Fetch transactions using internal id
    transactions = crud.get_transactions_by_account(
        db=db, account_id=db_bank_account.id
    )

    if not transactions:
        return schemas.AnalyticsResponse(
            yearlyTransactionData=[],
            monthlyTransactionData=[],
            weeklyTransactionData=[],
            yearlyBalanceData=[],
            monthlyBalanceData=[],
            weeklyBalanceData=[],
            yearlyLineSeries=[],
            monthlyLineSeries=[],
            weeklyLineSeries=[],
            pieExpense=[],
            pieIncome=[],
        )

    # Convert to DataFrame safely
    df = pd.DataFrame(
        [
            {
                "id": t.id,
                "amount": float(t.amount),
                "type": t.type,
                "category": t.category,
                "date": t.date,
            }
            for t in transactions
        ]
    )

    df["date"] = pd.to_datetime(df["date"])
    df["amount"] = df["amount"].astype(float)

    now = datetime.now()
    current_year = now.year
    current_month = now.month

    df_current_year = df[df["date"].dt.year == current_year]
    df_current_month = df_current_year[
        df_current_year["date"].dt.month == current_month
    ]

    # --- Helper Functions ---
    def format_data_for_chart(series):
        return [
            schemas.DataPoint(label=str(label), value=round(Decimal(value), 2))
            for label, value in series.items()
        ]

    def format_line_series_data(groups, prefix):
        income_points = []
        expense_points = []

        for label, group in groups:
            income = group[group["type"] == "CREDIT"]["amount"].sum()
            expense = group[group["type"] == "DEBIT"]["amount"].sum()

            income_points.append(
                schemas.LineSeriesDataPoint(x=str(label), y=round(Decimal(income), 2))
            )
            expense_points.append(
                schemas.LineSeriesDataPoint(x=str(label), y=round(Decimal(expense), 2))
            )

        return [
            schemas.LineSeries(id=f"{prefix}_income", data=income_points),
            schemas.LineSeries(id=f"{prefix}_expense", data=expense_points),
        ]

    # --- Transaction (Debit) Data ---
    yearly_transactions = (
        df[df["type"] == "DEBIT"].groupby(df["date"].dt.year)["amount"].sum()
    )

    monthly_transactions = (
        df_current_year[df_current_year["type"] == "DEBIT"]
        .groupby(
            df_current_year["date"].dt.month.apply(lambda x: calendar.month_abbr[x])
        )["amount"]
        .sum()
    )

    weekly_transactions = (
        df_current_month[df_current_month["type"] == "DEBIT"]
        .groupby(df_current_month["date"].dt.isocalendar().week)["amount"]
        .sum()
    )

    # --- Balance (Credit) Data ---
    yearly_balance = (
        df[df["type"] == "CREDIT"].groupby(df["date"].dt.year)["amount"].sum()
    )

    monthly_balance = (
        df_current_year[df_current_year["type"] == "CREDIT"]
        .groupby(
            df_current_year["date"].dt.month.apply(lambda x: calendar.month_abbr[x])
        )["amount"]
        .sum()
    )

    weekly_balance = (
        df_current_month[df_current_month["type"] == "CREDIT"]
        .groupby(df_current_month["date"].dt.isocalendar().week)["amount"]
        .sum()
    )

    # --- Line Series ---
    yearlyLineSeries = format_line_series_data(df.groupby(df["date"].dt.year), "yearly")
    monthlyLineSeries = format_line_series_data(
        df_current_year.groupby(
            df_current_year["date"].dt.month.apply(lambda x: calendar.month_abbr[x])
        ),
        "monthly",
    )
    weeklyLineSeries = format_line_series_data(
        df_current_month.groupby(df_current_month["date"].dt.isocalendar().week),
        "weekly",
    )

    # --- Pie Charts ---
    pieExpense = [
        schemas.PieChartData(
            id=category, label=category, value=round(Decimal(amount), 2)
        )
        for category, amount in df[df["type"] == "DEBIT"]
        .groupby("category")["amount"]
        .sum()
        .nlargest(5)
        .items()
    ]

    pieIncome = [
        schemas.PieChartData(
            id=category, label=category, value=round(Decimal(amount), 2)
        )
        for category, amount in df[df["type"] == "CREDIT"]
        .groupby("category")["amount"]
        .sum()
        .nlargest(5)
        .items()
    ]

    # --- Final Response ---
    return schemas.AnalyticsResponse(
        yearlyTransactionData=format_data_for_chart(yearly_transactions),
        monthlyTransactionData=format_data_for_chart(monthly_transactions),
        weeklyTransactionData=format_data_for_chart(weekly_transactions),
        yearlyBalanceData=format_data_for_chart(yearly_balance),
        monthlyBalanceData=format_data_for_chart(monthly_balance),
        weeklyBalanceData=format_data_for_chart(weekly_balance),
        yearlyLineSeries=yearlyLineSeries,
        monthlyLineSeries=monthlyLineSeries,
        weeklyLineSeries=weeklyLineSeries,
        pieExpense=pieExpense,
        pieIncome=pieIncome,
    )
