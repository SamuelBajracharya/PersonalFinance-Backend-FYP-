import pandas as pd
import numpy as np
from datetime import timedelta
import joblib
import tensorflow as tf
import warnings
import os

warnings.filterwarnings("ignore")

# Get the directory of the current script
AI_DIR = os.path.dirname(os.path.abspath(__file__))

def predict_next_day(
    user_id: str,
    category: str,
    budget_remaining: float,
    look_back: int = 30,
):
    prefix = f"GLOBAL_{category}"
    
    model_path_lstm = os.path.join(AI_DIR, f"lstm_{prefix}.keras")
    model_path_xgb = os.path.join(AI_DIR, f"xgb_{prefix}.pkl")
    scaler_path = os.path.join(AI_DIR, f"scaler_{prefix}.pkl")
    accounts_path = os.path.join(AI_DIR, f"accounts_{prefix}.pkl")
    transactions_path = os.path.join(AI_DIR, "transactions.csv")

    if not all(os.path.exists(p) for p in [model_path_lstm, model_path_xgb, scaler_path, accounts_path]):
        raise FileNotFoundError(f"Models for category '{category}' not found.")

    lstm_model = tf.keras.models.load_model(model_path_lstm)
    xgb_model = joblib.load(model_path_xgb)
    scaler = joblib.load(scaler_path)
    trained_accounts = joblib.load(accounts_path)
    
    df = pd.read_csv(transactions_path)
    df["date"] = pd.to_datetime(df["date"]).dt.date
    df["amount"] = pd.to_numeric(df["amount"], errors="coerce")
    df.dropna(subset=["amount"], inplace=True)

    daily_spend = (
        df.groupby(["account_id", "date", "category"])["amount"].sum().reset_index()
    )

    daily_spend = (
        df.groupby(["account_id", "date", "category"])["amount"].sum().reset_index()
    )

    # Filter daily_spend by category, but keep all account_ids
    category_daily_spend = daily_spend[daily_spend["category"] == category]

    # First, prepare the full historical data for all relevant accounts (trained + current user)
    # This df will be used to extract user_series and next_day_date later
    all_accounts_data_for_user_series = category_daily_spend.pivot(
        index="date", columns="account_id", values="amount"
    ).reindex(columns=list(set(trained_accounts) | {user_id}), fill_value=0) # Union of trained_accounts and current user_id

    # Fill in any missing dates in the historical data range for user series
    if not all_accounts_data_for_user_series.empty:
        full_dates_range_user_series = pd.date_range(
            all_accounts_data_for_user_series.index.min(), 
            all_accounts_data_for_user_series.index.max(), 
            freq="D"
        )
        all_accounts_data_for_user_series = all_accounts_data_for_user_series.reindex(full_dates_range_user_series).fillna(0)
        all_accounts_data_for_user_series.index = all_accounts_data_for_user_series.index.date
    else:
        # If no data for category, create an empty dataframe with user_id column
        all_accounts_data_for_user_series = pd.DataFrame(columns=[user_id])
    

    # Now, prepare the data specifically for the LSTM model and scaler.
    # This must ONLY include the columns the scaler was fitted on (i.e., trained_accounts).
    # Reindex with trained_accounts, filling missing accounts with 0
    lstm_input_for_scaling = category_daily_spend.pivot(
        index="date", columns="account_id", values="amount"
    ).reindex(columns=list(trained_accounts), fill_value=0)

    # Fill in any missing dates in the historical data range for LSTM input
    if not lstm_input_for_scaling.empty:
        full_dates_range_lstm = pd.date_range(
            lstm_input_for_scaling.index.min(), 
            lstm_input_for_scaling.index.max(), 
            freq="D"
        )
        lstm_input_for_scaling = lstm_input_for_scaling.reindex(full_dates_range_lstm).fillna(0)
        lstm_input_for_scaling.index = lstm_input_for_scaling.index.date
    else:
        # If no data for category, create an empty dataframe with trained_accounts columns
        lstm_input_for_scaling = pd.DataFrame(columns=list(trained_accounts))


    # Ensure the look_back period is available for prediction for the LSTM input
    if len(lstm_input_for_scaling) < look_back:
        padding_needed = look_back - len(lstm_input_for_scaling)
        
        # Only pad if there are columns to pad for
        if not lstm_input_for_scaling.empty:
            # Create a DataFrame of zeros for padding
            # Ensure the index for padding is correctly calculated to precede existing data
            if not lstm_input_for_scaling.empty and lstm_input_for_scaling.index.min():
                start_date_for_padding = pd.to_datetime(lstm_input_for_scaling.index.min()) - pd.to_timedelta(np.arange(padding_needed, 0, -1), unit="D")
            else: # If lstm_input_for_scaling is entirely empty, assume today as reference
                start_date_for_padding = pd.to_datetime('today').date() - pd.to_timedelta(np.arange(padding_needed, 0, -1), unit="D")
                
            padding_df = pd.DataFrame(
                0.0, 
                index=start_date_for_padding,
                columns=lstm_input_for_scaling.columns
            ).sort_index()
            
            lstm_input_for_scaling = pd.concat([padding_df, lstm_input_for_scaling]).tail(look_back)
            lstm_input_for_scaling.index = lstm_input_for_scaling.index.date
        else: # If lstm_input_for_scaling is empty, and we still need look_back, fill with all zeros for trained_accounts
            start_date_for_padding = pd.to_datetime('today').date() - pd.to_timedelta(np.arange(look_back, 0, -1), unit="D")
            lstm_input_for_scaling = pd.DataFrame(
                0.0, 
                index=start_date_for_padding,
                columns=list(trained_accounts)
            )
            lstm_input_for_scaling.index = lstm_input_for_scaling.index.date

    else:
        lstm_input_for_scaling = lstm_input_for_scaling.tail(look_back)

    # Check if lstm_input_for_scaling is still empty or has no columns after all processing
    if lstm_input_for_scaling.empty or lstm_input_for_scaling.shape[1] == 0:
        # Fallback for when no data is available even for trained accounts
        today = pd.to_datetime('today').date()
        next_day_date = today + timedelta(days=1)
        # Ensure we return valid types
        return 0.0, 0.0, "LOW", next_day_date, next_day_date.strftime("%A"), next_day_date.weekday(), 0.0


    last_days = lstm_input_for_scaling.values
    last_days_scaled = scaler.transform(last_days) # This should now have the correct number of features

    X_live = np.array([last_days_scaled])
    pred_scaled = lstm_model.predict(X_live, verbose=0)

    # Inverse transform the prediction. The LSTM predicts a single value (mean across accounts)
    # We use the shape of the scaled input to correctly inverse_transform
    pred_full = scaler.inverse_transform(
        np.repeat(pred_scaled, lstm_input_for_scaling.shape[1], axis=1)
    )

    # The predicted_amount is the mean of the inverse-transformed prediction across all accounts
    predicted_amount = pred_full.mean()

    # Determine next_day_date from the full user data series to ensure correct date progression
    next_day_date = pd.to_datetime(all_accounts_data_for_user_series.index.max()) + timedelta(days=1) if not all_accounts_data_for_user_series.empty else pd.to_datetime('today').date() + timedelta(days=1)

    # Extract user-specific series for risk calculation from the full historical data
    user_series = (
        all_accounts_data_for_user_series[user_id]
        if user_id in all_accounts_data_for_user_series.columns
        else pd.Series(0, index=all_accounts_data_for_user_series.index)
    )
    
    # Ensure user_series has enough data for rolling calculations
    if len(user_series) < 7: # rolling_7_mean/std requires at least 7 data points
        rolling_7_mean = 0.0
        rolling_7_std = 0.0
    else:
        rolling_7_mean = user_series.tail(7).mean()
        rolling_7_std = user_series.tail(7).std()

    live_features = pd.DataFrame(
        [
            {
                "day_of_week": next_day_date.weekday(),
                "rolling_7_mean": rolling_7_mean,
                "rolling_7_std": rolling_7_std,
                "lstm_predicted": predicted_amount, # This is a global prediction
            }
        ]
    )


    # Handle cases where live_features might have NaN for rolling_7_std if user_series is constant
    live_features.fillna(0, inplace=True)

    risk_prob = xgb_model.predict_proba(live_features)[0][1]

    is_over_budget = predicted_amount > budget_remaining
    risk_level = "LOW"

    if is_over_budget:
        risk_level = "HIGH"
    elif risk_prob > 0.6:
        risk_level = "MODERATE"

    return predicted_amount, risk_prob, risk_level, next_day_date, next_day_date.strftime("%A"), next_day_date.weekday(), rolling_7_mean