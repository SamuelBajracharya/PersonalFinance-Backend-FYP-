# ============================================
# SECTION 1: Install and Imports (Colab-ready)
# ============================================
# In Google Colab, uncomment this line once:
# !pip install yfinance scikit-learn pandas numpy

from __future__ import annotations

from dataclasses import dataclass
from statistics import NormalDist
from typing import Dict, List, Tuple

import numpy as np
import pandas as pd
import yfinance as yf
from sklearn.linear_model import LinearRegression
from sklearn.metrics import mean_absolute_error, mean_squared_error
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler


# ============================================
# SECTION 2: Core Utilities
# ============================================
@dataclass
class ModelArtifacts:
    ticker: str
    lag_days: int
    model: Pipeline
    train_returns: pd.Series
    test_returns: pd.Series
    test_predicted_returns: np.ndarray
    rmse: float
    mae: float
    directional_accuracy: float
    baseline_mean_return: float
    baseline_rmse: float
    baseline_mae: float
    baseline_directional_accuracy: float


def download_returns(ticker: str, period: str = "5y") -> pd.Series:
    """Download adjusted close prices and compute daily percentage returns."""
    data = yf.download(ticker, period=period, auto_adjust=True, progress=False)
    if data.empty:
        raise ValueError(f"No valid data found for ticker: {ticker}")

    if isinstance(data.columns, pd.MultiIndex):
        if "Close" not in data.columns.get_level_values(0):
            raise ValueError(f"No valid Close data found for ticker: {ticker}")
        close = data.xs("Close", axis=1, level=0)
    else:
        if "Close" not in data.columns:
            raise ValueError(f"No valid Close data found for ticker: {ticker}")
        close = data["Close"]

    if isinstance(close, pd.DataFrame):
        if close.empty:
            raise ValueError(f"No valid Close series found for ticker: {ticker}")
        close = close.iloc[:, 0]

    returns = close.pct_change().dropna().astype(float)
    returns.name = "return"
    return returns


def build_lagged_features(
    returns: pd.Series, lag_days: int = 5
) -> Tuple[pd.DataFrame, pd.Series]:
    """
    Build lagged feature matrix X and target y.
    y_t is predicted using [r_{t-1}, ..., r_{t-lag_days}].
    """
    if lag_days < 1:
        raise ValueError("lag_days must be >= 1")

    df = pd.DataFrame({"return": returns})
    for lag in range(1, lag_days + 1):
        df[f"lag_{lag}"] = df["return"].shift(lag)

    df = df.dropna()
    feature_cols = [f"lag_{lag}" for lag in range(1, lag_days + 1)]

    X = df[feature_cols]
    y = df["return"]
    return X, y


def chronological_split(
    X: pd.DataFrame,
    y: pd.Series,
    test_size: float = 0.2,
) -> Tuple[pd.DataFrame, pd.DataFrame, pd.Series, pd.Series]:
    """Chronological train-test split with no shuffling to avoid leakage."""
    if not 0 < test_size < 1:
        raise ValueError("test_size must be between 0 and 1")

    split_idx = int(len(X) * (1 - test_size))
    if split_idx <= 0 or split_idx >= len(X):
        raise ValueError("Not enough data after applying test_size")

    X_train = X.iloc[:split_idx].copy()
    X_test = X.iloc[split_idx:].copy()
    y_train = y.iloc[:split_idx].copy()
    y_test = y.iloc[split_idx:].copy()
    return X_train, X_test, y_train, y_test


def train_return_model(
    ticker: str,
    period: str = "5y",
    lag_days: int = 5,
    test_size: float = 0.2,
) -> ModelArtifacts:
    """
    Train linear regression on lagged returns.
    Uses StandardScaler + LinearRegression in a Pipeline (fit on train only).
    """
    returns = download_returns(ticker=ticker, period=period)
    if len(returns) <= lag_days + 30:
        raise ValueError("Not enough data for selected lag_days and split.")

    X, y = build_lagged_features(returns=returns, lag_days=lag_days)
    X_train, X_test, y_train, y_test = chronological_split(X, y, test_size=test_size)

    model = Pipeline(
        steps=[
            ("scaler", StandardScaler()),
            ("regressor", LinearRegression()),
        ]
    )

    model.fit(X_train, y_train)
    y_pred = model.predict(X_test)

    rmse = float(np.sqrt(mean_squared_error(y_test, y_pred)))
    mae = float(mean_absolute_error(y_test, y_pred))
    directional_acc = directional_accuracy(y_test, y_pred)

    baseline_mean_ret = float(y_train.mean())
    baseline_pred = np.full(len(y_test), baseline_mean_ret, dtype=float)
    baseline_rmse = float(np.sqrt(mean_squared_error(y_test, baseline_pred)))
    baseline_mae = float(mean_absolute_error(y_test, baseline_pred))
    baseline_directional_acc = directional_accuracy(y_test, baseline_pred)

    return ModelArtifacts(
        ticker=ticker,
        lag_days=lag_days,
        model=model,
        train_returns=y_train,
        test_returns=y_test,
        test_predicted_returns=y_pred,
        rmse=rmse,
        mae=mae,
        directional_accuracy=directional_acc,
        baseline_mean_return=baseline_mean_ret,
        baseline_rmse=baseline_rmse,
        baseline_mae=baseline_mae,
        baseline_directional_accuracy=baseline_directional_acc,
    )


# ============================================
# SECTION 3: Forecast and Risk Functions
# ============================================
def forecast_next_n_returns(
    model: Pipeline,
    recent_returns: pd.Series,
    lag_days: int,
    horizon_days: int,
) -> np.ndarray:
    """
    Recursive multi-step forecast of daily returns.
    Uses predicted returns as new lags for future steps.

    Limitation:
    Recursive forecasting compounds prediction error as horizon increases.
    """
    if horizon_days < 1:
        raise ValueError("horizon_days must be >= 1")
    if len(recent_returns) < lag_days:
        raise ValueError("Not enough recent_returns to create initial lag window")

    lag_buffer = list(recent_returns.iloc[-lag_days:].values)
    predictions: List[float] = []

    for _ in range(horizon_days):
        x = np.array(lag_buffer[-lag_days:][::-1], dtype=float).reshape(1, -1)
        next_ret = float(model.predict(x)[0])
        predictions.append(next_ret)
        lag_buffer.append(next_ret)

    return np.array(predictions, dtype=float)


def cumulative_return(daily_returns: np.ndarray) -> float:
    """Convert a vector of daily returns into cumulative return."""
    return float(np.prod(1 + daily_returns) - 1)


def directional_accuracy(y_true: pd.Series, y_pred: np.ndarray) -> float:
    """Share of predictions that match the true return direction."""
    y_true_arr = np.asarray(y_true, dtype=float)
    y_pred_arr = np.asarray(y_pred, dtype=float)
    if len(y_true_arr) == 0:
        raise ValueError("y_true must not be empty")

    correct_direction = np.sign(y_true_arr) == np.sign(y_pred_arr)
    return float(np.mean(correct_direction))


def scaled_volatility(historical_returns: pd.Series, horizon_days: int) -> float:
    """Scale daily volatility by sqrt(T)."""
    daily_vol = float(historical_returns.std(ddof=1))
    return float(daily_vol * np.sqrt(horizon_days))


def confidence_interval(
    expected_return: float,
    vol_scaled: float,
    confidence_level: float = 0.95,
) -> Tuple[float, float]:
    """Confidence interval around expected return for a chosen confidence level."""
    if not 0 < confidence_level < 1:
        raise ValueError("confidence_level must be between 0 and 1")

    z_score = float(NormalDist().inv_cdf((1 + confidence_level) / 2))
    margin = z_score * vol_scaled
    lower = expected_return - margin
    upper = expected_return + margin
    return float(lower), float(upper)


def predict_return_with_confidence(
    artifacts: ModelArtifacts,
    recent_returns: pd.Series,
    horizon_days: int,
    confidence_level: float = 0.95,
) -> Dict[str, float]:
    """
    Predict horizon cumulative return and confidence interval.
    Returns values in decimal form.
    """
    predicted_daily = forecast_next_n_returns(
        model=artifacts.model,
        recent_returns=recent_returns,
        lag_days=artifacts.lag_days,
        horizon_days=horizon_days,
    )

    expected_cum_return = cumulative_return(predicted_daily)
    vol_scaled = scaled_volatility(artifacts.train_returns, horizon_days)
    ci_low, ci_high = confidence_interval(
        expected_return=expected_cum_return,
        vol_scaled=vol_scaled,
        confidence_level=confidence_level,
    )

    return {
        "expected_return": expected_cum_return,
        "ci_low": ci_low,
        "ci_high": ci_high,
    }


# ============================================
# SECTION 4: Portfolio Aggregation
# ============================================
def portfolio_forecast(
    tickers: List[str],
    weights: List[float],
    period: str = "5y",
    lag_days: int = 5,
    test_size: float = 0.2,
    horizon_days: int = 30,
    confidence_level: float = 0.95,
) -> Dict[str, float]:
    """
    Aggregate multi-asset expected return and confidence range.
    - Expected return: weighted sum of each asset expected cumulative return
    - Volatility: covariance-based portfolio daily volatility scaled by sqrt(T)
    """
    if len(tickers) != len(weights):
        raise ValueError("tickers and weights must have the same length")

    w = np.array(weights, dtype=float)
    if np.isclose(w.sum(), 0):
        raise ValueError("weights must not sum to 0")
    w = w / w.sum()

    expected_returns = []
    returns_matrix = {}

    for ticker in tickers:
        returns = download_returns(ticker=ticker, period=period)
        artifacts = train_return_model(
            ticker=ticker,
            period=period,
            lag_days=lag_days,
            test_size=test_size,
        )
        pred = predict_return_with_confidence(
            artifacts=artifacts,
            recent_returns=artifacts.train_returns,
            horizon_days=horizon_days,
            confidence_level=confidence_level,
        )
        expected_returns.append(pred["expected_return"])
        returns_matrix[ticker] = artifacts.train_returns

    expected_portfolio_return = float(
        np.dot(w, np.array(expected_returns, dtype=float))
    )

    aligned_returns = pd.concat(returns_matrix.values(), axis=1, join="inner")
    aligned_returns.columns = list(returns_matrix.keys())
    cov_matrix = aligned_returns.cov().values

    portfolio_daily_vol = float(np.sqrt(w.T @ cov_matrix @ w))
    portfolio_vol_scaled = float(portfolio_daily_vol * np.sqrt(horizon_days))

    ci_low, ci_high = confidence_interval(
        expected_return=expected_portfolio_return,
        vol_scaled=portfolio_vol_scaled,
        confidence_level=confidence_level,
    )

    return {
        "expected_return": expected_portfolio_return,
        "ci_low": ci_low,
        "ci_high": ci_high,
    }


# ============================================
# SECTION 5: End-to-End Runner
# ============================================
def run_single_ticker_example(
    ticker: str = "AAPL",
    period: str = "5y",
    lag_days: int = 5,
    test_size: float = 0.2,
    horizon_days: int = 30,
    confidence_level: float = 0.95,
) -> Dict[str, float]:
    """
    Train, evaluate, and forecast for a single ticker.
    Returns metrics and prediction outputs as percentages.
    """
    full_returns = download_returns(ticker=ticker, period=period)
    artifacts = train_return_model(
        ticker=ticker,
        period=period,
        lag_days=lag_days,
        test_size=test_size,
    )
    pred = predict_return_with_confidence(
        artifacts=artifacts,
        recent_returns=artifacts.train_returns,
        horizon_days=horizon_days,
        confidence_level=confidence_level,
    )

    result = {
        "ticker": ticker,
        "horizon_days": horizon_days,
        "confidence_level_pct": confidence_level * 100,
        "expected_return_pct": pred["expected_return"] * 100,
        "ci_low_pct": pred["ci_low"] * 100,
        "ci_high_pct": pred["ci_high"] * 100,
        "rmse": artifacts.rmse,
        "mae": artifacts.mae,
        "directional_accuracy_pct": artifacts.directional_accuracy * 100,
        "baseline_mean_return_pct": artifacts.baseline_mean_return * 100,
        "baseline_rmse": artifacts.baseline_rmse,
        "baseline_mae": artifacts.baseline_mae,
        "baseline_directional_accuracy_pct": artifacts.baseline_directional_accuracy
        * 100,
    }
    return result


# ============================================
# SECTION 6: Demo Calls (Colab)
# ============================================
if __name__ == "__main__":
    single = run_single_ticker_example(
        ticker="AAPL",
        period="5y",
        lag_days=5,
        test_size=0.2,
        horizon_days=30,
    )

    print("Single Ticker Forecast")
    print(f"Ticker: {single['ticker']}")
    print(f"Horizon: {single['horizon_days']} days")
    print(f"Confidence Level (%): {single['confidence_level_pct']:.1f}")
    print(f"Expected Return (%): {single['expected_return_pct']:.2f}")
    print(
        f"{single['confidence_level_pct']:.1f}% Confidence Range (%): "
        f"[{single['ci_low_pct']:.2f}, {single['ci_high_pct']:.2f}]"
    )
    print(f"RMSE: {single['rmse']:.6f}")
    print(f"MAE: {single['mae']:.6f}")
    print(f"Directional Accuracy (%): {single['directional_accuracy_pct']:.2f}")
    print(f"Baseline Mean Return (%): {single['baseline_mean_return_pct']:.4f}")
    print(f"Baseline RMSE: {single['baseline_rmse']:.6f}")
    print(f"Baseline MAE: {single['baseline_mae']:.6f}")
    print(
        "Baseline Directional Accuracy (%): "
        f"{single['baseline_directional_accuracy_pct']:.2f}"
    )

    portfolio = portfolio_forecast(
        tickers=["AAPL", "MSFT", "GOOGL"],
        weights=[0.4, 0.35, 0.25],
        period="5y",
        lag_days=5,
        test_size=0.2,
        horizon_days=30,
        confidence_level=0.95,
    )

    print("\nPortfolio Forecast")
    print(f"Expected Return (%): {portfolio['expected_return'] * 100:.2f}")
    print(
        "95% Confidence Range (%): "
        f"[{portfolio['ci_low'] * 100:.2f}, {portfolio['ci_high'] * 100:.2f}]"
    )
