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
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta
import calendar
from decimal import Decimal
from app import crud

import pytz # Import pytz for timezone handling

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

    # Determine timezone of dataframe dates if any, and apply to 'now'
    now = datetime.now()
    if not df.empty and df["date"].dt.tz is not None:
        local_tz = df["date"].dt.tz
        now = now.astimezone(local_tz) # Make 'now' timezone-aware

    twelve_months_ago = now - relativedelta(months=11)
    df_last_12_months = df[df["date"] >= twelve_months_ago]
    
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
    # YEARLY LINE SERIES (YEAR-OVER-YEAR)
    # --------------------------
    yearly_groups = df.groupby(df["date"].dt.year)
    yearly_line_series = format_line_series_data(yearly_groups, "yearly")

    # --------------------------
    # MONTHLY LINE SERIES (LAST 12 MONTHS)
    # --------------------------
    monthly_line_series = []
    if not df_last_12_months.empty:
        df_last_12_months = df_last_12_months.copy()
        df_last_12_months["month_year"] = df_last_12_months["date"].dt.to_period("M")
        
        date_range = pd.date_range(start=twelve_months_ago, end=now, freq='MS').to_period('M')
        
        monthly_income = df_last_12_months[df_last_12_months['type'] == 'CREDIT'].groupby('month_year')['amount'].sum().reindex(date_range, fill_value=0)
        monthly_expenses = df_last_12_months[df_last_12_months['type'] == 'DEBIT'].groupby('month_year')['amount'].sum().reindex(date_range, fill_value=0)

        income_points = []
        expense_points = []
        for period in date_range:
            month_abbr = period.strftime('%b')
            income = monthly_income.get(period, 0)
            expense = monthly_expenses.get(period, 0)
            income_points.append(LineSeriesDataPoint(x=month_abbr, y=f"{income:.2f}"))
            expense_points.append(LineSeriesDataPoint(x=month_abbr, y=f"{expense:.2f}"))

        monthly_line_series = [
            LineSeries(id="monthly_income", data=income_points),
            LineSeries(id="monthly_expense", data=expense_points),
        ]
    else:
        empty_series = LineSeries(id="", data=[])
        monthly_line_series = [empty_series, empty_series]

    # --------------------------
    # WEEKLY LINE SERIES (CURRENT WEEK)
    # --------------------------
    start_of_week = now - timedelta(days=now.weekday())
    end_of_week = start_of_week + timedelta(days=6)
    df_current_week = df[(df['date'] >= start_of_week) & (df['date'] <= end_of_week)]

    weekly_line_series = []
    if not df_current_week.empty:
        df_current_week = df_current_week.copy()
        df_current_week['day_of_week'] = df_current_week['date'].dt.day_name()
        
        daily_groups = df_current_week.groupby('day_of_week')
        weekly_line_series = format_line_series_data(daily_groups, "weekly")

        # Ensure all days of the week are present
        days_of_week = list(calendar.day_name)
        existing_days = {p.x for s in weekly_line_series for p in s.data}
        for day in days_of_week:
            if day not in existing_days:
                for series in weekly_line_series:
                    series.data.append(LineSeriesDataPoint(x=day, y="0.00"))
        
        # Sort data by day of the week
        day_order = {day: i for i, day in enumerate(calendar.day_name)}
        for series in weekly_line_series:
            series.data.sort(key=lambda p: day_order[p.x])

    else:
        empty_series = LineSeries(id="", data=[])
        weekly_line_series = [empty_series, empty_series]


    return DashboardResponse(
        summary=summary_data,
        yearlyLineSeries=yearly_line_series,
        monthlyLineSeries=monthly_line_series,
        weeklyLineSeries=weekly_line_series,
    )
