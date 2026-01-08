from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.utils.deps import get_db, get_current_user
from app.models.user import User
from app.models.bank import BankAccount
from app.schemas.dashboard import (
    DashboardResponse,
    SummaryData,
    LineSeries,
    LineSeriesDataPoint,
)
from typing import List
from app.services.reward_evaluation import evaluate_rewards
from app.crud.budget import update_completed_budgets_for_user
import pandas as pd
from datetime import datetime
import calendar
from decimal import Decimal
from app import crud

router = APIRouter()


@router.get("/{external_id}", response_model=DashboardResponse)
async def get_dashboard_data(
    external_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    db_bank_account = (
        db.query(BankAccount)
        .filter(BankAccount.external_account_id == external_id)
        .first()
    )

    if not db_bank_account or db_bank_account.user_id != current_user.user_id:
        raise HTTPException(
            status_code=404, detail="Bank account not found or not owned by user"
        )
    
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
                totalIncome="0.00", totalExpenses="0.00", totalBalance="0.00"
            ),
            yearlyLineSeries=[empty_series, empty_series],
            monthlyLineSeries=[empty_series, empty_series],
            weeklyLineSeries=[empty_series, empty_series],
        )

    # Convert transactions to DataFrame
    df = pd.DataFrame(
        [
            {
                "amount": float(t.amount),
                "type": t.type,
                "date": t.date,
            }
            for t in transactions
        ]
    )

    df["date"] = pd.to_datetime(df["date"])
    df["amount"] = df["amount"].astype(float)

    # Summary totals
    total_income = df[df["type"] == "CREDIT"]["amount"].sum()
    total_expenses = df[df["type"] == "DEBIT"]["amount"].sum()
    total_balance = total_income - total_expenses

    summary_data = SummaryData(
        totalIncome=f"{total_income:.2f}",
        totalExpenses=f"{total_expenses:.2f}",
        totalBalance=f"{total_balance:.2f}",
    )

    now = datetime.now()
    current_year = now.year
    current_month = now.month

    df_current_year = df[df["date"].dt.year == current_year]
    df_current_month = df_current_year[
        df_current_year["date"].dt.month == current_month
    ]

    def format_line_series_data(groups, prefix):
        income_points = []
        expense_points = []

        for label, group in groups:
            income = group[group["type"] == "CREDIT"]["amount"].sum()
            expense = group[group["type"] == "DEBIT"]["amount"].sum()

            income_points.append(LineSeriesDataPoint(x=str(label), y=f"{income:.2f}"))
            expense_points.append(LineSeriesDataPoint(x=str(label), y=f"{expense:.2f}"))

        return [
            LineSeries(id=f"{prefix}_income", data=income_points),
            LineSeries(id=f"{prefix}_expense", data=expense_points),
        ]

    # --------------------------
    # YEARLY LINE SERIES
    # --------------------------
    yearly_groups = df.groupby(df["date"].dt.year)
    yearly_line_series = format_line_series_data(yearly_groups, "yearly")

    # --------------------------
    # MONTHLY LINE SERIES
    # --------------------------
    monthly_groups = df_current_year.groupby(df_current_year["date"].dt.month)
    monthly_line_series = format_line_series_data(monthly_groups, "monthly")

    # Convert month numbers → "Jan", "Feb", etc.
    for series in monthly_line_series:
        for point in series.data:
            point.x = calendar.month_abbr[int(point.x)]

    # --------------------------
    # WEEKLY LINE SERIES (FIXED TO 4 WEEKS)
    # --------------------------

    # Create week-of-month (1–4)
    if not df_current_month.empty:
        df_current_month = df_current_month.copy()
        df_current_month["week_of_month"] = (
            df_current_month["date"].dt.day - 1
        ) // 7 + 1

        weekly_groups = df_current_month.groupby("week_of_month")
        weekly_line_series = format_line_series_data(weekly_groups, "weekly")

        # Convert 1 → Week 1, etc.
        for series in weekly_line_series:
            for point in series.data:
                point.x = f"Week {point.x}"
    else:
        empty_series = LineSeries(id="", data=[])
        weekly_line_series = [empty_series, empty_series]

    return DashboardResponse(
        summary=summary_data,
        yearlyLineSeries=yearly_line_series,
        monthlyLineSeries=monthly_line_series,
        weeklyLineSeries=weekly_line_series,
    )
