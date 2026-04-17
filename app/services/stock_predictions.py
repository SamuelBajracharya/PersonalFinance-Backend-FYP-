import httpx
import numpy as np
import pandas as pd
import yfinance as yf
import zlib
import importlib
from datetime import date, timedelta

Nepse = None
try:
    nepse_module = importlib.import_module("nepse")
    Nepse = getattr(nepse_module, "Nepse", None)
except Exception:  # pragma: no cover - optional dependency
    Nepse = None

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
MONTE_CARLO_PATHS = 250
NEPSE_LOOKBACK_DAYS = 730


def _currency_for_market(prefer_nepse: bool) -> str:
    return "RS" if prefer_nepse else "$"


def _validate_force_source(force_source: str) -> str:
    normalized = (force_source or "auto").strip().lower()
    if normalized not in ALLOWED_FORCE_SOURCES:
        raise ValueError("force_source must be one of: auto, mock, placeholder")
    return normalized


def _extract_close_series_from_yahoo_frame(
    data: pd.DataFrame, symbol: str
) -> pd.Series:
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


def _download_yahoo_close_series(symbol: str, period: str = "2y") -> pd.Series:
    data = yf.download(symbol, period=period, auto_adjust=True, progress=False)
    return _extract_close_series_from_yahoo_frame(data, symbol)


def _download_nepse_close_series(
    symbol: str,
    lookback_days: int = NEPSE_LOOKBACK_DAYS,
) -> pd.Series:
    if Nepse is None:
        raise ValueError(
            "NEPSE provider is unavailable. Install with: pip install git+https://github.com/basic-bgnr/NepseUnofficialApi"
        )

    client = Nepse()
    client.setTLSVerification(False)

    end_date = date.today()
    start_date = end_date - timedelta(days=lookback_days)
    payload = client.getCompanyPriceVolumeHistory(
        symbol=symbol,
        start_date=start_date,
        end_date=end_date,
    )

    rows = payload.get("content", []) if isinstance(payload, dict) else payload
    if not rows:
        raise ValueError(f"No NEPSE history found for symbol: {symbol}")

    df = pd.DataFrame(rows)
    date_col = next(
        (col for col in ["businessDate", "date", "tradeDate"] if col in df.columns),
        None,
    )
    close_col = next(
        (
            col
            for col in [
                "closePrice",
                "closingPrice",
                "close",
                "lastTradedPrice",
                "ltp",
            ]
            if col in df.columns
        ),
        None,
    )

    if not date_col or not close_col:
        raise ValueError(
            f"Unexpected NEPSE payload for symbol {symbol}; missing date/close fields"
        )

    dates = pd.to_datetime(df[date_col], errors="coerce")
    close = pd.to_numeric(
        df[close_col].astype(str).str.replace(",", "", regex=False),
        errors="coerce",
    )
    series = pd.Series(close.values, index=dates).dropna().sort_index().astype(float)
    if series.empty:
        raise ValueError(f"No valid NEPSE close series found for symbol: {symbol}")
    return series


def _download_close_series(
    symbol: str,
    period: str = "2y",
    prefer_nepse: bool = False,
) -> pd.Series:
    normalized_symbol = symbol.strip().upper()
    nepse_symbol = normalized_symbol.removesuffix(".NEPSE")
    errors: list[str] = []

    providers = (
        [
            lambda: _download_nepse_close_series(nepse_symbol),
            lambda: _download_yahoo_close_series(normalized_symbol, period=period),
        ]
        if prefer_nepse
        else [
            lambda: _download_yahoo_close_series(normalized_symbol, period=period),
            lambda: _download_nepse_close_series(nepse_symbol),
        ]
    )

    for provider in providers:
        try:
            return provider()
        except Exception as exc:
            errors.append(str(exc))

    raise ValueError(
        f"No market data found for symbol: {symbol}. Provider errors: {' | '.join(errors)}"
    )


def _estimate_noise_std(returns: pd.Series, predicted_returns: np.ndarray) -> float:
    if len(predicted_returns) == 0:
        return max(float(returns.std(ddof=1)), 0.001)

    aligned_actual = returns.iloc[-len(predicted_returns) :].to_numpy(dtype=float)
    residuals = aligned_actual - predicted_returns
    residual_std = float(np.std(residuals, ddof=1)) if len(residuals) > 1 else 0.0
    historical_std = float(returns.std(ddof=1))

    return float(max(residual_std, historical_std * 0.35, 0.001))


def _simulate_fluctuating_price_path(
    symbol: str,
    start_price: float,
    base_daily_returns: np.ndarray,
    noise_std: float,
    horizon_days: int,
    reference_date: str,
) -> list[dict]:
    seed = zlib.adler32(f"{symbol}:{horizon_days}:{reference_date}".encode("utf-8"))
    rng = np.random.default_rng(seed)

    simulated_returns = rng.normal(
        loc=base_daily_returns,
        scale=noise_std,
        size=(MONTE_CARLO_PATHS, horizon_days),
    )
    simulated_returns = np.clip(simulated_returns, -0.2, 0.2)

    growth = np.cumprod(1.0 + simulated_returns, axis=1)
    simulated_prices = np.maximum(growth * start_price, 0.01)

    representative_idx = 0
    representative_path = simulated_prices[representative_idx]
    lower_band = np.quantile(simulated_prices, 0.1, axis=0)
    upper_band = np.quantile(simulated_prices, 0.9, axis=0)

    return [
        {
            "day": day,
            "price": float(representative_path[day - 1]),
            "low_price": float(lower_band[day - 1]),
            "high_price": float(upper_band[day - 1]),
        }
        for day in range(1, horizon_days + 1)
    ]


def _build_price_paths(
    symbol: str,
    horizon_days: int,
    prefer_nepse: bool = False,
) -> tuple[list[dict], list[dict]]:
    close = _download_close_series(symbol, period="2y", prefer_nepse=prefer_nepse)
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
        returns_override=returns,
    )
    predicted_daily_returns = forecast_next_n_returns(
        model=artifacts.model,
        recent_returns=returns,
        lag_days=artifacts.lag_days,
        horizon_days=horizon_days,
    )

    start_price = float(close.iloc[-1])
    noise_std = _estimate_noise_std(
        returns=returns, predicted_returns=artifacts.test_predicted_returns
    )
    future_points = _simulate_fluctuating_price_path(
        symbol=symbol,
        start_price=start_price,
        base_daily_returns=predicted_daily_returns,
        noise_std=noise_std,
        horizon_days=horizon_days,
        reference_date=close.index[-1].date().isoformat(),
    )

    return past_points, future_points


def _attach_price_paths(
    prediction: dict,
    symbol: str,
    horizon_days: int,
    prefer_nepse: bool = False,
) -> dict:
    past_price_history, future_price_prediction = _build_price_paths(
        symbol,
        horizon_days,
        prefer_nepse=prefer_nepse,
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


def _extract_user_id_from_payload(payload) -> str | None:
    if not isinstance(payload, dict):
        return None
    user_id = payload.get("user_id")
    if isinstance(user_id, str) and user_id.strip():
        return user_id.strip()
    return None


def _with_path_fallback(path: str) -> tuple[str, ...]:
    clean_path = f"/{path.lstrip('/')}"
    if clean_path.endswith("/"):
        return (clean_path, clean_path.rstrip("/"))
    return (clean_path, f"{clean_path}/")


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
    endpoint_candidates = ["/stock-instruments", "/instruments", "/investments"]

    try:
        with httpx.Client(timeout=10.0) as client:
            me_response = client.get(
                f"{EXTERNAL_BANK_API_BASE_URL}/users/me/", headers=headers
            )
        me_response.raise_for_status()
        external_user_id = _extract_user_id_from_payload(me_response.json())
        if external_user_id:
            endpoint_candidates.insert(0, f"/users/{external_user_id}/stocks")
    except Exception:
        pass

    for path in endpoint_candidates:
        try:
            items = []
            for path_variant in _with_path_fallback(path):
                with httpx.Client(timeout=10.0) as client:
                    response = client.get(
                        f"{EXTERNAL_BANK_API_BASE_URL}{path_variant}", headers=headers
                    )
                response.raise_for_status()
                items = _extract_instruments_from_payload(response.json())
                if items:
                    break

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
        close_series = _download_close_series(symbol, period="5y", prefer_nepse=True)
        returns_series = close_series.pct_change().dropna()
        prediction = run_single_ticker_example(
            ticker=symbol,
            horizon_days=horizon_days,
            confidence_level=confidence_level,
            returns_override=returns_series,
        )
        prediction = _attach_price_paths(
            prediction,
            symbol,
            horizon_days,
            prefer_nepse=True,
        )
        prediction["instrument"] = symbol
        prediction["source"] = source
        prediction["currency"] = _currency_for_market(prefer_nepse=True)
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
    user_instrument = get_stock_instrument_by_user_and_symbol(db, user_id, symbol)

    prefer_nepse = symbol.endswith(".NEPSE") or user_instrument is not None
    close_series = _download_close_series(
        symbol, period="5y", prefer_nepse=prefer_nepse
    )
    returns_series = close_series.pct_change().dropna()

    prediction = run_single_ticker_example(
        ticker=symbol,
        horizon_days=horizon_days,
        confidence_level=confidence_level,
        returns_override=returns_series,
    )
    prediction = _attach_price_paths(
        prediction,
        symbol,
        horizon_days,
        prefer_nepse=prefer_nepse,
    )
    prediction["instrument"] = symbol
    prediction["currency"] = _currency_for_market(prefer_nepse=prefer_nepse)

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
