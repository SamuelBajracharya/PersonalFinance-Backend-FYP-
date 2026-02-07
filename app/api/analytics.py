from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List
import pandas as pd
from datetime import datetime, timezone
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
    time_horizon: str = Query(
        "30d", description="Time horizon: 7d, 30d, 90d, calendar_month"
    ),
    year: int = Query(None, description="Year for monthly analytics (e.g. 2025)"),
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

    df["date"] = pd.to_datetime(df["date"]).dt.tz_convert(timezone.utc)
    df["amount"] = df["amount"].astype(float)

    # Use timezone-aware UTC for all date operations
    now = datetime.now(timezone.utc)

    # Determine start_date and end_date based on time_horizon
    if time_horizon == "7d":
        start_date = now - pd.Timedelta(days=6)
    elif time_horizon == "30d":
        start_date = now - pd.Timedelta(days=29)
    elif time_horizon == "90d":
        start_date = now - pd.Timedelta(days=89)
    elif time_horizon == "calendar_month":
        start_date = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    else:
        start_date = now - pd.Timedelta(days=29)
    end_date = now

    # Filter for the selected time horizon
    df_horizon = df[(df["date"] >= start_date) & (df["date"] <= end_date)].copy()

    # For weekly stats, use current month
    df_current_month = df[
        (df["date"].dt.year == now.year) & (df["date"].dt.month == now.month)
    ]

    # --- Helper Functions ---
    def format_data_for_chart(series):
        # This function now expects a series with a pre-formatted string index
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

    # --- Monthly Data Calculation ---
    # If a year is specified, filter df for that year for monthly analytics
    if year is not None:
        df_monthly = df[df["date"].dt.year == year]
        # Create labels for all months in the selected year
        all_months_labels = [
            pd.Timestamp(year=year, month=m, day=1).strftime("%b %Y")
            for m in range(1, 13)
        ]
    else:
        df_monthly = df
        # Default: last 12 months from start_date to end_date
        all_months_labels = (
            pd.date_range(start=start_date, end=end_date, freq="MS")
            .strftime("%b %Y")
            .tolist()
        )

    def process_monthly_data(series, labels):
        # Reindex to include all 12 months, filling missing ones with 0
        series = series.reindex(labels, fill_value=0)
        return series

    # --- Transaction (Debit) Data ---
    yearly_transactions = (
        df[df["type"] == "DEBIT"].groupby(df["date"].dt.year)["amount"].sum()
    )

    # Group by 'Month YYYY' string format
    if year is not None:
        monthly_transactions_series = (
            df_monthly[df_monthly["type"] == "DEBIT"]
            .groupby(df_monthly["date"].dt.strftime("%b %Y"))["amount"]
            .sum()
        )
    else:
        monthly_transactions_series = (
            df_horizon[df_horizon["type"] == "DEBIT"]
            .groupby(df_horizon["date"].dt.strftime("%b %Y"))["amount"]
            .sum()
        )
    monthly_transactions = process_monthly_data(
        monthly_transactions_series, all_months_labels
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

    if year is not None:
        monthly_balance_series = (
            df_monthly[df_monthly["type"] == "CREDIT"]
            .groupby(df_monthly["date"].dt.strftime("%b %Y"))["amount"]
            .sum()
        )
    else:
        monthly_balance_series = (
            df_horizon[df_horizon["type"] == "CREDIT"]
            .groupby(df_horizon["date"].dt.strftime("%b %Y"))["amount"]
            .sum()
        )
    monthly_balance = process_monthly_data(monthly_balance_series, all_months_labels)

    weekly_balance = (
        df_current_month[df_current_month["type"] == "CREDIT"]
        .groupby(df_current_month["date"].dt.isocalendar().week)["amount"]
        .sum()
    )

    # --- Line Series ---
    yearlyLineSeries = format_line_series_data(df.groupby(df["date"].dt.year), "yearly")

    # Monthly Line Series
    monthly_income_series = (
        df_last_12_months[df_last_12_months["type"] == "CREDIT"]
        .groupby(df_last_12_months["date"].dt.strftime("%b %Y"))["amount"]
        .sum()
    )
    monthly_income = process_monthly_data(monthly_income_series, all_months_labels)

    monthly_expense_series = (
        df_last_12_months[df_last_12_months["type"] == "DEBIT"]
        .groupby(df_last_12_months["date"].dt.strftime("%b %Y"))["amount"]
        .sum()
    )
    monthly_expense = process_monthly_data(monthly_expense_series, all_months_labels)

    income_points = [
        schemas.LineSeriesDataPoint(x=str(label), y=round(Decimal(value), 2))
        for label, value in monthly_income.items()
    ]
    expense_points = [
        schemas.LineSeriesDataPoint(x=str(label), y=round(Decimal(value), 2))
        for label, value in monthly_expense.items()
    ]

    monthlyLineSeries = [
        schemas.LineSeries(id="monthly_income", data=income_points),
        schemas.LineSeries(id="monthly_expense", data=expense_points),
    ]

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

    # --- Freshness Metadata ---
    from app.crud.bank_sync_status import get_sync_status

    sync_status = get_sync_status(db, current_user.user_id)
    is_data_fresh = False
    last_successful_sync = None
    last_attempted_sync = None
    sync_status_value = None
    failure_reason = None
    if sync_status:
        last_successful_sync = sync_status.last_successful_sync
        last_attempted_sync = sync_status.last_attempted_sync
        sync_status_value = sync_status.sync_status
        failure_reason = sync_status.failure_reason
        from datetime import date

        is_data_fresh = (
            last_successful_sync is not None
            and last_successful_sync.date() == date.today()
        )
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
        is_data_fresh=is_data_fresh,
        last_successful_sync=last_successful_sync,
        last_attempted_sync=last_attempted_sync,
        sync_status=sync_status_value,
        failure_reason=failure_reason,
    )
