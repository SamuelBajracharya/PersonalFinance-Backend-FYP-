
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
import uuid
from typing import List
import pandas as pd
from datetime import datetime
import calendar

from app import crud, schemas
from app.utils.deps import get_db, get_current_user
from app.models.user import User
from app.models.bank import BankAccount, Transaction

router = APIRouter()

@router.get("/analytics/{account_id}", response_model=schemas.AnalyticsResponse)
def get_financial_analytics(
    account_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # Verify account ownership
    db_bank_account = db.query(BankAccount).filter(BankAccount.id == account_id).first()
    if db_bank_account is None or db_bank_account.user_id != current_user.user_id:
        raise HTTPException(status_code=404, detail="Bank account not found or not owned by user")

    # Fetch transactions
    transactions = crud.get_transactions_by_account(db=db, account_id=account_id)
    if not transactions:
        # Return an empty analytics response if no transactions
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

    # Convert to Pandas DataFrame
    df = pd.DataFrame([t.__dict__ for t in transactions])
    df["date"] = pd.to_datetime(df["date"])
    df["amount"] = df["amount"].astype(float)

    # Filter for current year and month for monthly and weekly data
    current_year = datetime.now().year
    current_month = datetime.now().month

    df_current_year = df[df["date"].dt.year == current_year]
    df_current_month = df_current_year[df_current_year["date"].dt.month == current_month]

    # Helper to format data for charts
    def format_data_for_chart(series, label_map=None):
        result = []
        for label, value in series.items():
            if label_map:
                label = label_map.get(label, str(label))
            result.append(schemas.DataPoint(label=str(label), value=round(Decimal(value), 2)))
        return result

    def format_line_series_data(df_grouped, id_prefix, label_map=None):
        income_data = []
        expense_data = []
        for label, group in df_grouped:
            income = group[group["type"] == "CREDIT"]["amount"].sum()
            expense = group[group["type"] == "DEBIT"]["amount"].sum()
            if label_map:
                label = label_map.get(label, str(label))
            income_data.append(schemas.LineSeriesDataPoint(x=str(label), y=round(Decimal(income), 2)))
            expense_data.append(schemas.LineSeriesDataPoint(x=str(label), y=round(Decimal(expense), 2)))
        return [
            schemas.LineSeries(id=f"{id_prefix}income", data=income_data),
            schemas.LineSeries(id=f"{id_prefix}expense", data=expense_data),
        ]

    # Transaction Data (Total Expenses - DEBIT)
    yearly_transactions = df[df["type"] == "DEBIT"].groupby(df["date"].dt.year)["amount"].sum()
    monthly_transactions = df_current_year[df_current_year["type"] == "DEBIT"].groupby(df_current_year["date"].dt.month.apply(lambda x: calendar.month_abbr[x]))["amount"].sum()
    weekly_transactions = df_current_month[df_current_month["type"] == "DEBIT"].groupby(df_current_month["date"].dt.isocalendar().week.apply(lambda x: f"Week {x}"))["amount"].sum()

    yearlyTransactionData = format_data_for_chart(yearly_transactions)
    monthlyTransactionData = format_data_for_chart(monthly_transactions)
    weeklyTransactionData = format_data_for_chart(weekly_transactions)

    # Balance Data (Total Income - CREDIT)
    yearly_balance = df[df["type"] == "CREDIT"].groupby(df["date"].dt.year)["amount"].sum()
    monthly_balance = df_current_year[df_current_year["type"] == "CREDIT"].groupby(df_current_year["date"].dt.month.apply(lambda x: calendar.month_abbr[x]))["amount"].sum()
    weekly_balance = df_current_month[df_current_month["type"] == "CREDIT"].groupby(df_current_month["date"].dt.isocalendar().week.apply(lambda x: f"Week {x}"))["amount"].sum()

    yearlyBalanceData = format_data_for_chart(yearly_balance)
    monthlyBalanceData = format_data_for_chart(monthly_balance)
    weeklyBalanceData = format_data_for_chart(weekly_balance)

    # Line Series Data
    yearlyLineSeries = format_line_series_data(df.groupby(df["date"].dt.year), "yearly")
    monthlyLineSeries = format_line_series_data(df_current_year.groupby(df_current_year["date"].dt.month.apply(lambda x: calendar.month_abbr[x])), "monthly")
    weeklyLineSeries = format_line_series_data(df_current_month.groupby(df_current_month["date"].dt.isocalendar().week.apply(lambda x: f"Week {x}")), "weekly")

    # Pie Charts
    pieExpense = []
    top_5_expenses = df[df["type"] == "DEBIT"].groupby("category")["amount"].sum().nlargest(5)
    for category, amount in top_5_expenses.items():
        pieExpense.append(schemas.PieChartData(id=category, label=category, value=round(Decimal(amount), 2)))

    pieIncome = []
    top_5_income = df[df["type"] == "CREDIT"].groupby("category")["amount"].sum().nlargest(5)
    for category, amount in top_5_income.items():
        pieIncome.append(schemas.PieChartData(id=category, label=category, value=round(Decimal(amount), 2)))

    return schemas.AnalyticsResponse(
        yearlyTransactionData=yearlyTransactionData,
        monthlyTransactionData=monthlyTransactionData,
        weeklyTransactionData=weeklyTransactionData,
        yearlyBalanceData=yearlyBalanceData,
        monthlyBalanceData=monthlyBalanceData,
        weeklyBalanceData=weeklyBalanceData,
        yearlyLineSeries=yearlyLineSeries,
        monthlyLineSeries=monthlyLineSeries,
        weeklyLineSeries=weeklyLineSeries,
        pieExpense=pieExpense,
        pieIncome=pieIncome,
    )
