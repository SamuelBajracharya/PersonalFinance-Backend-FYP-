from pydantic import BaseModel
from typing import List


class SummaryData(BaseModel):
    totalIncome: str
    totalExpenses: str
    totalBalance: str
    savingRate: str


class LineSeriesDataPoint(BaseModel):
    x: str
    y: str


class LineSeries(BaseModel):
    id: str
    data: List[LineSeriesDataPoint]


class RecentTransactionItem(BaseModel):
    id: str
    date: str
    type: str
    amount: str
    category: str | None = None
    description: str | None = None
    merchant: str | None = None


class BudgetGoalItem(BaseModel):
    id: str
    category: str
    budgetAmount: str
    spentAmount: str
    remainingBudget: str
    usagePct: str
    status: str


class StockItem(BaseModel):
    id: str
    symbol: str
    name: str | None = None
    quantity: str
    currentPrice: str | None = None
    averageBuyPrice: str | None = None
    marketValue: str | None = None


class AISuggestionItem(BaseModel):
    category: str
    suggestion: str


class ExpenseCategoryChartItem(BaseModel):
    id: str
    label: str
    value: str


class DashboardAISuggestionsResponse(BaseModel):
    suggestions: List[AISuggestionItem]


class DashboardResponse(BaseModel):
    summary: SummaryData
    yearlyLineSeries: List[LineSeries]
    monthlyLineSeries: List[LineSeries]
    recentTransactions: List[RecentTransactionItem] = []
    topBudgetGoals: List[BudgetGoalItem] = []
    topStocks: List[StockItem] = []
    aiSuggestions: List[AISuggestionItem] = []
    monthlyExpenseCategoryChart: List[ExpenseCategoryChartItem] = []
    yearlyExpenseCategoryChart: List[ExpenseCategoryChartItem] = []
