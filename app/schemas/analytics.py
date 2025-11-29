
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
