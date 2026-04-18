import pandas as pd
import numpy as np
from datetime import timedelta
import joblib
import tensorflow as tf
import warnings
import os
import re

warnings.filterwarnings("ignore")

# Get the directory of the current script
AI_DIR = os.path.dirname(os.path.abspath(__file__))


def _category_model_key(category: str) -> str:
    key = re.sub(r"[^A-Za-z0-9]+", "_", str(category).strip())
    key = re.sub(r"_+", "_", key).strip("_")
    return key or "Uncategorized"


def _resolve_model_paths(category: str) -> dict[str, str]:
    category_key = _category_model_key(category)
    prefix_candidates = [f"GLOBAL_{category_key}", f"GLOBAL_{category}"]

    for prefix in prefix_candidates:
        model_path_lstm = os.path.join(AI_DIR, f"lstm_{prefix}.keras")
        model_path_xgb = os.path.join(AI_DIR, f"xgb_{prefix}.pkl")
        scaler_path = os.path.join(AI_DIR, f"scaler_{prefix}.pkl")
        accounts_path = os.path.join(AI_DIR, f"accounts_{prefix}.pkl")
        meta_path = os.path.join(AI_DIR, f"meta_{prefix}.pkl")

        if all(
            os.path.exists(path)
            for path in [model_path_lstm, model_path_xgb, scaler_path, accounts_path]
        ):
            return {
                "prefix": prefix,
                "model_path_lstm": model_path_lstm,
                "model_path_xgb": model_path_xgb,
                "scaler_path": scaler_path,
                "accounts_path": accounts_path,
                "meta_path": meta_path,
            }

    raise FileNotFoundError(f"Models for category '{category}' not found.")


def _build_category_series_for_user(
    df: pd.DataFrame,
    user_id: str,
    category: str,
) -> pd.Series:
    daily_spend = (
        df.groupby(["account_id", "date", "category"])["amount"].sum().reset_index()
    )
    category_daily_spend = daily_spend[daily_spend["category"] == category]

    if category_daily_spend.empty:
        return pd.Series(dtype=float)

    user_data = category_daily_spend[
        category_daily_spend["account_id"].astype(str) == str(user_id)
    ]
    if not user_data.empty:
        series = user_data.set_index("date")["amount"].sort_index()
    else:
        # Fallback to global category behavior when user-specific history is unavailable.
        panel = category_daily_spend.pivot(
            index="date", columns="account_id", values="amount"
        ).fillna(0)
        series = panel.mean(axis=1)

    full_dates = pd.date_range(series.index.min(), series.index.max(), freq="D")
    series = series.reindex(full_dates).fillna(0.0).astype(float)
    return series


def predict_next_day(
    user_id: str,
    category: str,
    budget_remaining: float,
    look_back: int = 30,
):
    paths = _resolve_model_paths(category)
    model_path_lstm = paths["model_path_lstm"]
    model_path_xgb = paths["model_path_xgb"]
    scaler_path = paths["scaler_path"]
    accounts_path = paths["accounts_path"]
    meta_path = paths["meta_path"]
    transactions_path = os.path.join(AI_DIR, "transactions.csv")

    lstm_model = tf.keras.models.load_model(model_path_lstm)
    xgb_model = joblib.load(model_path_xgb)
    scaler = joblib.load(scaler_path)
    trained_accounts = joblib.load(accounts_path)
    metadata = joblib.load(meta_path) if os.path.exists(meta_path) else {}
    effective_look_back = int(metadata.get("look_back", look_back))
    fallback_amount = float(metadata.get("fallback_amount", 0.0))
    lstm_quality = float(metadata.get("lstm_quality", 0.5))
    risk_threshold = float(metadata.get("risk_threshold", 0.6))
    xgb_feature_columns = metadata.get(
        "xgb_feature_columns",
        [
            "day_of_week",
            "day_of_month",
            "is_weekend",
            "lag_1_amount",
            "lag_2_amount",
            "lag_3_amount",
            "rolling_3_mean",
            "rolling_7_mean",
            "rolling_14_mean",
            "rolling_7_std",
            "rolling_14_std",
            "trend_7",
            "lstm_predicted",
        ],
    )

    df = pd.read_csv(transactions_path)
    df["date"] = pd.to_datetime(df["date"]).dt.date
    df["amount"] = pd.to_numeric(df["amount"], errors="coerce")
    df.dropna(subset=["amount"], inplace=True)

    user_series = _build_category_series_for_user(df, user_id, category)
    if user_series.empty:
        # Fallback for when no data is available even for trained accounts
        today = pd.to_datetime("today").date()
        next_day_date = today + timedelta(days=1)
        # Ensure we return valid types
        return (
            0.0,
            0.0,
            "LOW",
            next_day_date,
            next_day_date.strftime("%A"),
            next_day_date.weekday(),
            0.0,
        )

    series_values = user_series.to_numpy().astype(float)
    if len(series_values) < effective_look_back:
        pad = np.zeros(effective_look_back - len(series_values), dtype=float)
        last_window = np.concatenate([pad, series_values])
    else:
        last_window = series_values[-effective_look_back:]

    scaled_window = scaler.transform(last_window.reshape(-1, 1)).reshape(-1)
    X_live = scaled_window.reshape(1, effective_look_back, 1)
    pred_scaled = lstm_model.predict(X_live, verbose=0).reshape(-1)
    predicted_amount_raw = float(
        scaler.inverse_transform(pred_scaled.reshape(-1, 1)).reshape(-1)[0]
    )

    last_date = pd.to_datetime(user_series.index.max())
    next_day_date = last_date + timedelta(days=1)

    lag_1_amount = float(series_values[-1]) if len(series_values) >= 1 else 0.0
    lag_2_amount = float(series_values[-2]) if len(series_values) >= 2 else lag_1_amount
    lag_3_amount = float(series_values[-3]) if len(series_values) >= 3 else lag_2_amount

    rolling_3_mean = (
        float(np.mean(series_values[-3:])) if len(series_values) >= 3 else lag_1_amount
    )
    rolling_7_mean = (
        float(np.mean(series_values[-7:]))
        if len(series_values) >= 7
        else rolling_3_mean
    )
    rolling_14_mean = (
        float(np.mean(series_values[-14:]))
        if len(series_values) >= 14
        else rolling_7_mean
    )
    rolling_7_std = (
        float(np.std(series_values[-7:], ddof=1)) if len(series_values) >= 7 else 0.0
    )
    rolling_14_std = (
        float(np.std(series_values[-14:], ddof=1))
        if len(series_values) >= 14
        else rolling_7_std
    )
    trend_7 = lag_1_amount - (
        float(series_values[-8]) if len(series_values) >= 8 else lag_1_amount
    )

    fallback_from_history = rolling_7_mean if rolling_7_mean > 0 else fallback_amount
    blend_weight = max(0.0, min(1.0, lstm_quality))
    predicted_amount = (
        blend_weight * predicted_amount_raw
        + (1.0 - blend_weight) * fallback_from_history
    )
    predicted_amount = max(0.0, float(predicted_amount))

    live_features = pd.DataFrame(
        [
            {
                "day_of_week": next_day_date.weekday(),
                "day_of_month": next_day_date.day,
                "is_weekend": int(next_day_date.weekday() >= 5),
                "lag_1_amount": lag_1_amount,
                "lag_2_amount": lag_2_amount,
                "lag_3_amount": lag_3_amount,
                "rolling_3_mean": rolling_3_mean,
                "rolling_7_mean": rolling_7_mean,
                "rolling_7_std": rolling_7_std,
                "rolling_14_mean": rolling_14_mean,
                "rolling_14_std": rolling_14_std,
                "trend_7": trend_7,
                "lstm_predicted": predicted_amount,
            }
        ]
    )

    live_features = live_features.reindex(columns=xgb_feature_columns, fill_value=0.0)

    # Handle cases where live_features might have NaN for rolling_7_std if user_series is constant
    live_features.fillna(0, inplace=True)

    risk_prob = xgb_model.predict_proba(live_features)[0][1]

    is_over_budget = predicted_amount > budget_remaining
    risk_level = "LOW"

    if is_over_budget:
        risk_level = "HIGH"
    elif risk_prob > risk_threshold:
        risk_level = "MODERATE"

    return (
        predicted_amount,
        risk_prob,
        risk_level,
        next_day_date,
        next_day_date.strftime("%A"),
        next_day_date.weekday(),
        rolling_7_mean,
    )
