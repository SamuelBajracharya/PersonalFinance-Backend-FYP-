import httpx
import numpy as np
import pandas as pd
import yfinance as yf

from app.crud.stock_instrument import (
    get_stock_instrument_by_user_and_symbol,
    get_stock_instruments_by_user,
)
from app.models.bank import BankAccount
from ai.stock_prediction_model.stock_return_forecast_colab import (
    forecast_next_n_returns,
    train_return_model,
    run_single_ticker_example,
)
from app.services.bank_sync import EXTERNAL_BANK_API_BASE_URL

ALLOWED_FORCE_SOURCES = {"auto", "mock", "placeholder"}


def _validate_force_source(force_source: str) -> str:
    normalized = (force_source or "auto").strip().lower()
    if normalized not in ALLOWED_FORCE_SOURCES:
        raise ValueError("force_source must be one of: auto, mock, placeholder")
    return normalized


def _download_close_series(symbol: str, period: str = "2y") -> pd.Series:
    data = yf.download(symbol, period=period, auto_adjust=True, progress=False)
    if data.empty:
        raise ValueError(f"No market data found for symbol: {symbol}")

    if isinstance(data.columns, pd.MultiIndex):
        if "Close" not in data.columns.get_level_values(0):
            raise ValueError(f"No Close data found for symbol: {symbol}")
        close = data.xs("Close", axis=1, level=0)
    else:
        if "Close" not in data.columns:
            raise ValueError(f"No Close data found for symbol: {symbol}")
        close = data["Close"]

    if isinstance(close, pd.DataFrame):
        close = close.iloc[:, 0]

    return close.dropna().astype(float)


def _build_price_paths(symbol: str, horizon_days: int) -> tuple[list[dict], list[dict]]:
    close = _download_close_series(symbol, period="2y")
    if close.empty:
        return [], []

    history_window = max(horizon_days, 30)
    past = close.tail(history_window)
    past_points = [
        {"date": idx.date().isoformat(), "price": float(value)}
        for idx, value in past.items()
    ]

    returns = close.pct_change().dropna()
    artifacts = train_return_model(
        ticker=symbol,
        period="5y",
        lag_days=5,
        test_size=0.2,
    )
    predicted_daily_returns = forecast_next_n_returns(
        model=artifacts.model,
        recent_returns=returns,
        lag_days=artifacts.lag_days,
        horizon_days=horizon_days,
    )

    start_price = float(close.iloc[-1])
    future_points: list[dict] = []
    current_price = start_price
    for day in range(1, horizon_days + 1):
        current_price *= float(1 + predicted_daily_returns[day - 1])
        future_points.append(
            {
                "day": day,
                "price": float(current_price),
            }
        )

    return past_points, future_points


def _attach_price_paths(prediction: dict, symbol: str, horizon_days: int) -> dict:
    past_price_history, future_price_prediction = _build_price_paths(
        symbol, horizon_days
    )
    prediction["past_price_history"] = past_price_history
    prediction["future_price_prediction"] = future_price_prediction
    return prediction


def _extract_instruments_from_payload(payload) -> list[dict]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if not isinstance(payload, dict):
        return []

    for key in ("stock_instruments", "instruments", "investments", "data"):
        value = payload.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
    return []


def _normalize_instrument(raw_item: dict) -> dict | None:
    symbol = (raw_item.get("symbol") or raw_item.get("ticker") or "").strip().upper()
    if not symbol:
        return None

    quantity = raw_item.get("quantity")
    return {
        "symbol": symbol,
        "name": raw_item.get("name"),
        "quantity": float(quantity) if quantity is not None else None,
        "currency": raw_item.get("currency"),
    }


def _get_external_user_instruments(db, user_id: str) -> list[dict]:
    account = (
        db.query(BankAccount)
        .filter(
            BankAccount.user_id == user_id,
            BankAccount.is_active == True,
            BankAccount.bank_token != None,
        )
        .first()
    )
    if not account or not account.bank_token:
        return []

    headers = {"Authorization": f"Bearer {account.bank_token}"}
    for path in ("/stock-instruments", "/instruments", "/investments"):
        try:
            with httpx.Client(timeout=10.0) as client:
                response = client.get(
                    f"{EXTERNAL_BANK_API_BASE_URL}{path}", headers=headers
                )
            response.raise_for_status()
            items = _extract_instruments_from_payload(response.json())
            normalized = []
            for item in items:
                parsed = _normalize_instrument(item)
                if parsed:
                    normalized.append(parsed)
            if normalized:
                return normalized
        except Exception:
            continue

    return []


def predict_for_user_instruments(
    db,
    user_id: str,
    horizon_days: int,
    confidence_level: float = 0.95,
    force_source: str = "auto",
):
    selected_source = _validate_force_source(force_source)

    external_instruments = _get_external_user_instruments(db, user_id)
    placeholder_instruments = get_stock_instruments_by_user(db, user_id)

    if selected_source == "mock":
        instruments = external_instruments
        source = "mock_api"
    elif selected_source == "placeholder":
        instruments = placeholder_instruments
        source = "placeholder"
    else:
        if external_instruments:
            instruments = external_instruments
            source = "mock_api"
        else:
            instruments = placeholder_instruments
            source = "placeholder"

    results = []

    for instrument in instruments:
        symbol = (
            instrument["symbol"] if isinstance(instrument, dict) else instrument.symbol
        )
        prediction = run_single_ticker_example(
            ticker=symbol,
            horizon_days=horizon_days,
            confidence_level=confidence_level,
        )
        prediction = _attach_price_paths(prediction, symbol, horizon_days)
        prediction["instrument"] = symbol
        prediction["source"] = source
        prediction["quantity"] = (
            instrument.get("quantity")
            if isinstance(instrument, dict)
            else (
                float(instrument.quantity) if instrument.quantity is not None else None
            )
        )
        prediction["name"] = (
            instrument.get("name") if isinstance(instrument, dict) else instrument.name
        )
        results.append(prediction)

    return results


def predict_for_instrument(
    db,
    user_id: str,
    instrument: str,
    horizon_days: int,
    confidence_level: float = 0.95,
    force_source: str = "auto",
):
    selected_source = _validate_force_source(force_source)
    symbol = instrument.strip().upper()
    external_instruments = _get_external_user_instruments(db, user_id)
    external_map = {item["symbol"]: item for item in external_instruments}

    prediction = run_single_ticker_example(
        ticker=symbol,
        horizon_days=horizon_days,
        confidence_level=confidence_level,
    )
    prediction = _attach_price_paths(prediction, symbol, horizon_days)

    user_instrument = get_stock_instrument_by_user_and_symbol(db, user_id, symbol)
    prediction["instrument"] = symbol

    if selected_source == "mock":
        if symbol in external_map:
            prediction["source"] = "mock_api"
            prediction["quantity"] = external_map[symbol].get("quantity")
            prediction["name"] = external_map[symbol].get("name")
        else:
            prediction["source"] = "available"
            prediction["quantity"] = None
            prediction["name"] = None
    elif selected_source == "placeholder":
        if user_instrument:
            prediction["source"] = "placeholder"
            prediction["quantity"] = (
                float(user_instrument.quantity)
                if user_instrument.quantity is not None
                else None
            )
            prediction["name"] = user_instrument.name
        else:
            prediction["source"] = "available"
            prediction["quantity"] = None
            prediction["name"] = None
    elif symbol in external_map:
        prediction["source"] = "mock_api"
        prediction["quantity"] = external_map[symbol].get("quantity")
        prediction["name"] = external_map[symbol].get("name")
    elif user_instrument:
        prediction["source"] = "placeholder"
        prediction["quantity"] = (
            float(user_instrument.quantity)
            if user_instrument.quantity is not None
            else None
        )
        prediction["name"] = user_instrument.name
    else:
        prediction["source"] = "available"
        prediction["quantity"] = None
        prediction["name"] = None

    return prediction
