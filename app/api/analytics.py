from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List
import pandas as pd
from datetime import datetime, timezone
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
    time_horizon: str | None = Query(
        None,
        description="Time horizon: 1m/30d/calendar_month (4 weeks), 3m/90d, 1y/year (all years), 7d",
    ),
    year: int = Query(None, description="Year for monthly analytics (e.g. 2025)"),
    startDate: str = Query(
        None,
        description="ISO start date for analytics filter (e.g. 2025-12-24T18:15:00.000Z)",
    ),
    endDate: str = Query(
        None,
        description="ISO end date for analytics filter (e.g. 2025-12-31T18:14:59.999Z)",
    ),
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
            momGrowth=[],
            momGrowthSeries=[],
        )

    # Convert to DataFrame safely
    df = pd.DataFrame(
        [
            {
                "id": t.id,
                "amount": float(t.amount),
                "type": t.type,
                "category": t.category,
                "description": t.description,
                "merchant": t.merchant,
                "date": t.date,
            }
            for t in transactions
        ]
    )

    df["date"] = pd.to_datetime(df["date"]).dt.tz_convert(timezone.utc)
    df["amount"] = df["amount"].astype(float)

    # Use timezone-aware UTC for all date operations
    now = pd.Timestamp(datetime.now(timezone.utc))

    def to_utc_timestamp(value: str) -> pd.Timestamp:
        ts = pd.to_datetime(value)
        return (
            ts.tz_localize(timezone.utc)
            if ts.tzinfo is None
            else ts.tz_convert(timezone.utc)
        )

    normalized_horizon = (time_horizon or "").strip().lower()

    # Determine unified window used by ALL analytics charts.
    if startDate and endDate:
        try:
            start_date = to_utc_timestamp(startDate)
            end_date = to_utc_timestamp(endDate)
        except Exception:
            raise HTTPException(
                status_code=400,
                detail="Invalid startDate or endDate format. Use ISO format.",
            )
    elif year is not None:
        start_date = pd.Timestamp(year=year, month=1, day=1, tz=timezone.utc)
        end_date = pd.Timestamp(
            year=year, month=12, day=31, hour=23, minute=59, second=59, tz=timezone.utc
        )
    elif normalized_horizon in {"", "1y", "year", "all", "all_years"}:
        # No explicit selection defaults to all available years in data.
        start_date = df["date"].min()
        end_date = df["date"].max()
    elif normalized_horizon in {"3m", "90d"}:
        end_date = now
        start_date = end_date - pd.DateOffset(months=3)
    elif normalized_horizon in {"1m", "30d", "calendar_month"}:
        end_date = now
        start_date = end_date - pd.Timedelta(days=27)
    elif normalized_horizon == "7d":
        end_date = now
        start_date = end_date - pd.Timedelta(days=6)
    else:
        end_date = now
        start_date = end_date - pd.Timedelta(days=27)

    if end_date < start_date:
        raise HTTPException(
            status_code=400, detail="endDate must be on or after startDate"
        )

    # Filter for the selected unified horizon.
    df_window = df[(df["date"] >= start_date) & (df["date"] <= end_date)].copy()

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

    def pct_growth(current: float, previous: float) -> Decimal | None:
        if previous == 0:
            return None
        return round(Decimal(((current - previous) / previous) * 100), 2)

    def classify_discretionary(row) -> str:
        text = " ".join(
            [
                str(row.get("category") or ""),
                str(row.get("description") or ""),
                str(row.get("merchant") or ""),
            ]
        ).lower()

        non_discretionary_keywords = {
            "utility",
            "electricity",
            "water",
            "gas",
            "internet",
            "rent",
            "maintenance",
            "insurance",
            "medical",
            "hospital",
            "pharmacy",
            "school",
            "education",
            "tuition",
            "loan",
            "emi",
            "debt",
            "grocer",
            "grocery",
            "supermarket",
        }

        discretionary_keywords = {
            "dining",
            "restaurant",
            "cafe",
            "coffee",
            "entertainment",
            "movie",
            "shopping",
            "fashion",
            "taxi",
            "ride",
            "travel",
            "fuel",
            "gym",
            "subscription",
            "delivery",
            "snack",
            "fast food",
            "food",
            "transport",
        }

        if any(keyword in text for keyword in non_discretionary_keywords):
            return "non_discretionary"

        if any(keyword in text for keyword in discretionary_keywords):
            return "discretionary"

        category = str(row.get("category") or "").lower().strip()
        needs_categories = {
            "utilities",
            "maintenance",
            "rent",
            "insurance",
            "healthcare",
            "education",
            "groceries",
        }

        if category in needs_categories:
            return "non_discretionary"

        return "discretionary"

    # --- Monthly Data Calculation ---
    if year is not None:
        df_monthly = df_window
        # Create labels for all months in the selected year
        all_months_labels = [
            pd.Timestamp(year=year, month=m, day=1).strftime("%b %Y")
            for m in range(1, 13)
        ]
    else:
        df_monthly = df_window
        labels_start = pd.Timestamp(start_date).replace(
            day=1, hour=0, minute=0, second=0, microsecond=0
        )
        labels_end = pd.Timestamp(end_date).replace(
            day=1, hour=0, minute=0, second=0, microsecond=0
        )
        # Use months fully covering the selected window.
        all_months_labels = (
            pd.date_range(start=labels_start, end=labels_end, freq="MS")
            .strftime("%b %Y")
            .tolist()
        )

    def process_monthly_data(series, labels):
        # Reindex to include all 12 months, filling missing ones with 0
        series = series.reindex(labels, fill_value=0)
        return series

    # --- Transaction (Debit) Data ---
    yearly_transactions = (
        df_window[df_window["type"] == "DEBIT"]
        .groupby(df_window["date"].dt.year)["amount"]
        .sum()
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
            df_window[df_window["type"] == "DEBIT"]
            .groupby(df_window["date"].dt.strftime("%b %Y"))["amount"]
            .sum()
        )
    monthly_transactions = process_monthly_data(
        monthly_transactions_series, all_months_labels
    )

    weekly_transactions = (
        df_window[df_window["type"] == "DEBIT"]
        .groupby(df_window["date"].dt.strftime("%G-W%V"))["amount"]
        .sum()
    )

    # --- Balance (Credit) Data ---
    yearly_balance = (
        df_window[df_window["type"] == "CREDIT"]
        .groupby(df_window["date"].dt.year)["amount"]
        .sum()
    )

    if year is not None:
        monthly_balance_series = (
            df_monthly[df_monthly["type"] == "CREDIT"]
            .groupby(df_monthly["date"].dt.strftime("%b %Y"))["amount"]
            .sum()
        )
    else:
        monthly_balance_series = (
            df_window[df_window["type"] == "CREDIT"]
            .groupby(df_window["date"].dt.strftime("%b %Y"))["amount"]
            .sum()
        )
    monthly_balance = process_monthly_data(monthly_balance_series, all_months_labels)

    weekly_balance = (
        df_window[df_window["type"] == "CREDIT"]
        .groupby(df_window["date"].dt.strftime("%G-W%V"))["amount"]
        .sum()
    )

    # --- Line Series ---
    yearlyLineSeries = format_line_series_data(
        df_window.groupby(df_window["date"].dt.year), "yearly"
    )

    # Monthly Line Series
    # Monthly line series uses the same unified selected window.
    df_last_12_months = df_window.copy()

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

    df_weekly = df_window.copy()
    df_weekly["year_week"] = df_weekly["date"].dt.strftime("%G-W%V")
    weeklyLineSeries = format_line_series_data(df_weekly.groupby("year_week"), "weekly")

    # --- Pie Charts ---
    pieExpense = [
        schemas.PieChartData(
            id=category, label=category, value=round(Decimal(amount), 2)
        )
        for category, amount in df_window[df_window["type"] == "DEBIT"]
        .groupby("category")["amount"]
        .sum()
        .nlargest(5)
        .items()
    ]

    pieIncome = [
        schemas.PieChartData(
            id=category, label=category, value=round(Decimal(amount), 2)
        )
        for category, amount in df_window[df_window["type"] == "CREDIT"]
        .groupby("category")["amount"]
        .sum()
        .nlargest(5)
        .items()
    ]

    # --- New Advisor-Focused Charts ---
    total_income = float(df_window[df_window["type"] == "CREDIT"]["amount"].sum())
    total_expense = float(df_window[df_window["type"] == "DEBIT"]["amount"].sum())
    ratio_pct = (total_expense / total_income * 100) if total_income > 0 else 0.0

    if ratio_pct >= 90:
        gauge_zone = "high_pressure"
        gauge_insight = "Expense-to-income ratio is above 90%. Cash-flow margin is thin and needs active control."
    elif ratio_pct >= 75:
        gauge_zone = "watch"
        gauge_insight = "Expense-to-income ratio is in a caution zone. Reducing variable spend can improve buffer."
    else:
        gauge_zone = "healthy"
        gauge_insight = "Expense-to-income ratio is in a healthier range with better room for savings."

    expense_income_gauge = schemas.ExpenseIncomeGauge(
        totalIncome=round(Decimal(total_income), 2),
        totalExpenses=round(Decimal(total_expense), 2),
        expenseToIncomeRatioPct=round(Decimal(ratio_pct), 2),
        zone=gauge_zone,
        advisorInsight=gauge_insight,
    )

    trend_start = pd.Timestamp(start_date).replace(
        day=1, hour=0, minute=0, second=0, microsecond=0
    )
    trend_end = pd.Timestamp(end_date)
    if trend_end.tzinfo is None:
        trend_end = trend_end.tz_localize(timezone.utc)

    df_trend = df_window.copy()
    month_labels = (
        pd.date_range(start=trend_start, end=trend_end, freq="MS")
        .strftime("%b %Y")
        .tolist()
    )

    monthly_income_for_growth = (
        df_trend[df_trend["type"] == "CREDIT"]
        .groupby(df_trend["date"].dt.strftime("%b %Y"))["amount"]
        .sum()
        .reindex(month_labels, fill_value=0)
    )
    monthly_expense_for_growth = (
        df_trend[df_trend["type"] == "DEBIT"]
        .groupby(df_trend["date"].dt.strftime("%b %Y"))["amount"]
        .sum()
        .reindex(month_labels, fill_value=0)
    )

    mom_growth = []
    income_growth_points = []
    expense_growth_points = []
    previous_income = None
    previous_expense = None
    for label in month_labels:
        income_val = float(monthly_income_for_growth[label])
        expense_val = float(monthly_expense_for_growth[label])

        income_growth = (
            pct_growth(income_val, previous_income)
            if previous_income is not None
            else None
        )
        expense_growth = (
            pct_growth(expense_val, previous_expense)
            if previous_expense is not None
            else None
        )

        mom_growth.append(
            schemas.MoMGrowthPoint(
                label=label,
                income=round(Decimal(income_val), 2),
                expense=round(Decimal(expense_val), 2),
                incomeGrowthPct=income_growth,
                expenseGrowthPct=expense_growth,
            )
        )

        income_growth_points.append(
            schemas.LineSeriesDataPoint(
                x=label,
                y=income_growth if income_growth is not None else Decimal("0.00"),
            )
        )
        expense_growth_points.append(
            schemas.LineSeriesDataPoint(
                x=label,
                y=expense_growth if expense_growth is not None else Decimal("0.00"),
            )
        )

        previous_income = income_val
        previous_expense = expense_val

    mom_growth_series = [
        schemas.LineSeries(id="mom_income_growth_pct", data=income_growth_points),
        schemas.LineSeries(id="mom_expense_growth_pct", data=expense_growth_points),
    ]

    debit_df = df_window[df_window["type"] == "DEBIT"].copy()
    if debit_df.empty:
        discretionary_total = 0.0
        non_discretionary_total = 0.0
    else:
        debit_df["discretionary_group"] = debit_df.apply(classify_discretionary, axis=1)
        discretionary_total = float(
            debit_df[debit_df["discretionary_group"] == "discretionary"]["amount"].sum()
        )
        non_discretionary_total = float(
            debit_df[debit_df["discretionary_group"] == "non_discretionary"][
                "amount"
            ].sum()
        )

    total_split = discretionary_total + non_discretionary_total
    discretionary_ratio = (
        (discretionary_total / total_split) * 100 if total_split > 0 else 0.0
    )
    non_discretionary_ratio = (
        (non_discretionary_total / total_split) * 100 if total_split > 0 else 0.0
    )

    discretionary_split = schemas.DiscretionarySplit(
        discretionary=round(Decimal(discretionary_total), 2),
        nonDiscretionary=round(Decimal(non_discretionary_total), 2),
        discretionaryRatioPct=round(Decimal(discretionary_ratio), 2),
        nonDiscretionaryRatioPct=round(Decimal(non_discretionary_ratio), 2),
        segments=[
            schemas.DiscretionarySplitSegment(
                id="discretionary",
                label="Wants",
                value=round(Decimal(discretionary_total), 2),
            ),
            schemas.DiscretionarySplitSegment(
                id="non_discretionary",
                label="Needs",
                value=round(Decimal(non_discretionary_total), 2),
            ),
        ],
        advisorInsight=(
            "A higher Wants share indicates more flexible spend that can be trimmed without affecting essentials."
            if discretionary_ratio >= 50
            else "Most spend is concentrated in Needs, so savings gains may require structural optimization."
        ),
    )

    savings_rate_points = []
    for label in month_labels:
        income_val = float(monthly_income_for_growth[label])
        expense_val = float(monthly_expense_for_growth[label])
        net_val = income_val - expense_val
        savings_rate = (net_val / income_val * 100) if income_val > 0 else 0.0

        savings_rate_points.append(
            schemas.SavingsRatePoint(
                label=label,
                income=round(Decimal(income_val), 2),
                expense=round(Decimal(expense_val), 2),
                netSavings=round(Decimal(net_val), 2),
                savingsRatePct=round(Decimal(savings_rate), 2),
            )
        )

    total_surplus = sum(float(point.netSavings) for point in savings_rate_points)
    avg_savings_rate = (
        sum(float(point.savingsRatePct) for point in savings_rate_points)
        / len(savings_rate_points)
        if savings_rate_points
        else 0.0
    )

    if len(savings_rate_points) >= 2:
        rate_delta = float(savings_rate_points[-1].savingsRatePct) - float(
            savings_rate_points[0].savingsRatePct
        )
    else:
        rate_delta = 0.0

    if rate_delta > 2:
        savings_trend = "improving"
        savings_insight = "Savings rate trend is improving, which supports stronger long-term cash resilience."
    elif rate_delta < -2:
        savings_trend = "declining"
        savings_insight = "Savings rate trend is declining, which can signal upcoming cash-flow pressure."
    else:
        savings_trend = "stable"
        savings_insight = "Savings rate trend is stable. Consistent control of variable expenses can lift this further."

    savings_rate_trend = schemas.SavingsRateTrend(
        points=savings_rate_points,
        totalNetSurplus=round(Decimal(total_surplus), 2),
        avgSavingsRatePct=round(Decimal(avg_savings_rate), 2),
        trend=savings_trend,
        advisorInsight=savings_insight,
    )

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

        # Convert to ISO strings for schema
        if last_successful_sync is not None:
            last_successful_sync = last_successful_sync.isoformat()
        if last_attempted_sync is not None:
            last_attempted_sync = last_attempted_sync.isoformat()
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
        expenseIncomeGauge=expense_income_gauge,
        momGrowth=mom_growth,
        momGrowthSeries=mom_growth_series,
        discretionarySplit=discretionary_split,
        savingsRateTrend=savings_rate_trend,
        is_data_fresh=is_data_fresh,
        last_successful_sync=last_successful_sync,
        last_attempted_sync=last_attempted_sync,
        sync_status=sync_status_value,
        failure_reason=failure_reason,
    )
