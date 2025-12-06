from pydantic import BaseModel
from typing import List

class SummaryData(BaseModel):
    totalIncome: str
    totalExpenses: str
    totalBalance: str

class LineSeriesDataPoint(BaseModel):
    x: str
    y: str

class LineSeries(BaseModel):
    id: str
    data: List[LineSeriesDataPoint]

class DashboardResponse(BaseModel):
    summary: SummaryData
    yearlyLineSeries: List[LineSeries]
    monthlyLineSeries: List[LineSeries]
    weeklyLineSeries: List[LineSeries]
