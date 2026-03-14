from pydantic import BaseModel
from typing import List, Dict, Any
from decimal import Decimal


class DataPoint(BaseModel):
    label: str
    value: Decimal


class LineSeriesDataPoint(BaseModel):
    x: str
    y: Decimal


class LineSeries(BaseModel):
    id: str
    data: List[LineSeriesDataPoint]


class PieChartData(BaseModel):
    id: str
    label: str
    value: Decimal


class ExpenseIncomeGauge(BaseModel):
    totalIncome: Decimal
    totalExpenses: Decimal
    expenseToIncomeRatioPct: Decimal
    zone: str
    advisorInsight: str


class MoMGrowthPoint(BaseModel):
    label: str
    income: Decimal
    expense: Decimal
    incomeGrowthPct: Decimal | None = None
    expenseGrowthPct: Decimal | None = None


class DiscretionarySplitSegment(BaseModel):
    id: str
    label: str
    value: Decimal


class DiscretionarySplit(BaseModel):
    discretionary: Decimal
    nonDiscretionary: Decimal
    discretionaryRatioPct: Decimal
    nonDiscretionaryRatioPct: Decimal
    segments: List[DiscretionarySplitSegment]
    advisorInsight: str


class SavingsRatePoint(BaseModel):
    label: str
    income: Decimal
    expense: Decimal
    netSavings: Decimal
    savingsRatePct: Decimal


class SavingsRateTrend(BaseModel):
    points: List[SavingsRatePoint]
    totalNetSurplus: Decimal
    avgSavingsRatePct: Decimal
    trend: str
    advisorInsight: str


class AnalyticsResponse(BaseModel):
    yearlyTransactionData: List[DataPoint]
    monthlyTransactionData: List[DataPoint]
    weeklyTransactionData: List[DataPoint]

    yearlyBalanceData: List[DataPoint]
    monthlyBalanceData: List[DataPoint]
    weeklyBalanceData: List[DataPoint]

    yearlyLineSeries: List[LineSeries]
    monthlyLineSeries: List[LineSeries]
    weeklyLineSeries: List[LineSeries]

    pieExpense: List[PieChartData]
    pieIncome: List[PieChartData]

    expenseIncomeGauge: ExpenseIncomeGauge | None = None
    momGrowth: List[MoMGrowthPoint] = []
    momGrowthSeries: List[LineSeries] = []
    discretionarySplit: DiscretionarySplit | None = None
    savingsRateTrend: SavingsRateTrend | None = None

    is_data_fresh: bool = True
    last_successful_sync: str | None = None
    last_attempted_sync: str | None = None
    sync_status: str | None = None
    failure_reason: str | None = None
