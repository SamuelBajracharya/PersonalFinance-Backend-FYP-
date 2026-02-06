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

    is_data_fresh: bool = True
    last_successful_sync: str | None = None
    last_attempted_sync: str | None = None
    sync_status: str | None = None
    failure_reason: str | None = None
