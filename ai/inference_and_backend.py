# predict_next_day_console.py
import pandas as pd
import numpy as np
from datetime import timedelta
import joblib
import tensorflow as tf
import warnings

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

warnings.filterwarnings("ignore")

# DATABASE CONFIG
DATABASE_URL = "postgresql://postgres:samuel@localhost:5432/test"

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

create_table_query = text("""
CREATE TABLE IF NOT EXISTS daily_predictions (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR(50) NOT NULL,
    prediction_date DATE NOT NULL,
    category VARCHAR(50) NOT NULL,
    day_of_week VARCHAR(20) NOT NULL,
    day_of_week_id INTEGER NOT NULL,
    rolling_7_day_avg DOUBLE PRECISION NOT NULL,
    budget_remaining DOUBLE PRECISION NOT NULL,
    predicted_amount DOUBLE PRECISION NOT NULL,
    risk_probability DOUBLE PRECISION NOT NULL,
    risk_level VARCHAR(20) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
""")

db = SessionLocal()
db.execute(create_table_query)
db.commit()
db.close()


# MAIN PREDICTION FUNCTION
def predict_next_day(
    transactions_file: str,
    account_id: str,
    category: str,
    budget_remaining: float,
    look_back: int = 30
):

    print("\n--- Loading Models & Data ---")

    prefix = f"{account_id}_{category}"

    lstm_model = tf.keras.models.load_model(f"lstm_{prefix}.keras")
    xgb_model = joblib.load(f"xgb_{prefix}.pkl")
    scaler = joblib.load(f"scaler_{prefix}.pkl")
    food_scaler = joblib.load(f"food_scaler_{prefix}.pkl")
    model_columns = joblib.load(f"columns_{prefix}.pkl")

    df = pd.read_csv(transactions_file)
    df["date"] = pd.to_datetime(df["date"]).dt.date
    df["amount"] = pd.to_numeric(df["amount"], errors="coerce")
    df.dropna(subset=["amount"], inplace=True)

    # DATA PREPARATION
    daily_spend = df.groupby(
        ["account_id", "date", "category"]
    )["amount"].sum().reset_index()

    user_data = daily_spend[daily_spend["account_id"] == account_id]

    lstm_input_raw = user_data.pivot(
        index="date",
        columns="category",
        values="amount"
    ).fillna(0)

    full_dates = pd.date_range(
        start=lstm_input_raw.index.min(),
        end=lstm_input_raw.index.max(),
        freq="D"
    )

    lstm_input = lstm_input_raw.reindex(full_dates).fillna(0)

    for col in model_columns:
        if col not in lstm_input.columns:
            lstm_input[col] = 0

    lstm_input = lstm_input[model_columns]

    # LSTM PREDICTION
    last_days = lstm_input.tail(look_back).values
    last_days_scaled = scaler.transform(last_days)

    X_live = np.array([last_days_scaled])
    prediction_scaled = lstm_model.predict(X_live, verbose=0)

    predicted_amount = food_scaler.inverse_transform(
        prediction_scaled
    )[0][0]

    next_day_date = lstm_input.index.max() + timedelta(days=1)

    # FEATURE ENGINEERING (XGB)
    rolling_7_mean = lstm_input[category].tail(7).mean()
    rolling_7_std = lstm_input[category].tail(7).std()

    live_features = pd.DataFrame([{
        "day_of_week": next_day_date.dayofweek,
        "rolling_7_mean": rolling_7_mean,
        "rolling_7_std": rolling_7_std,
        "lstm_predicted": predicted_amount
    }])

    risk_prob = xgb_model.predict_proba(live_features)[0][1]

    # OUTPUT REPORT
    print("\n[PREDICTIVE BUDGET ANALYZER - NEXT DAY RISK REPORT]")
    print("--------------------------------------------------")
    print(f"Prediction Date: {next_day_date}")
    print(f"Category: {category}")
    print(f"Day of Week: {next_day_date.strftime('%A')} (ID: {next_day_date.dayofweek})")
    print(f"Rolling 7-Day Avg: NPR {rolling_7_mean:,.2f}")
    print(f"User's Budget Remaining: NPR {budget_remaining:,.2f}")
    print("--------------------------------------------------")
    print(f"LSTM Forecast (Predicted Amount): NPR {predicted_amount:,.2f}")
    print(f"XGBoost Risk Probability: {risk_prob:.2f}")

    # RISK LOGIC 
    is_over_budget = predicted_amount > budget_remaining
    risk_level = "LOW"

    if is_over_budget:
        risk_level = "HIGH"
        print("\nCRITICAL: OVER BUDGET & HIGH SPEND")
        print(
            f"Warning: Predicted NPR {predicted_amount:,.2f} "
            f"exceeds budget ({budget_remaining})."
        )
        if risk_prob > 0.5:
            print("This is also statistically unusual (High Risk Spike).")

    elif risk_prob > 0.6:
        risk_level = "MODERATE"
        print("\nCAUTION: SPENDING SPIKE DETECTED")
        print("Predicted spending is significantly higher than your recent average.")

    else:
        print("\nSAFE: LOW RISK DETECTED")
        print("Spending is within normal limits and budget.")

    # SAVE TO DATABASE (BACKEND)
    print("\n--- Saving Prediction to Database ---")

    db = SessionLocal()

    insert_query = text("""
    INSERT INTO daily_predictions (
        user_id,
        prediction_date,
        category,
        day_of_week,
        day_of_week_id,
        rolling_7_day_avg,
        budget_remaining,
        predicted_amount,
        risk_probability,
        risk_level
    )
    VALUES (
        :user_id,
        :prediction_date,
        :category,
        :day_of_week,
        :day_of_week_id,
        :rolling_7_day_avg,
        :budget_remaining,
        :predicted_amount,
        :risk_probability,
        :risk_level
    )
    """)

    db.execute(insert_query, {
        "user_id": account_id,
        "prediction_date": next_day_date,
        "category": category,
        "day_of_week": next_day_date.strftime("%A"),
        "day_of_week_id": next_day_date.dayofweek,
        "rolling_7_day_avg": float(rolling_7_mean),
        "budget_remaining": float(budget_remaining),
        "predicted_amount": float(predicted_amount),
        "risk_probability": float(risk_prob),
        "risk_level": risk_level
    })

    db.commit()
    db.close()

    print("Prediction saved successfully.")

    # FINAL SUMMARY
    print("\n--- FINAL RISK SUMMARY ---")
    print(f"Risk Level: {risk_level}")
    print("Prediction completed successfully.")

    return risk_level


# EXAMPLE RUN
if __name__ == "__main__":
    predict_next_day(
        transactions_file="transactions.csv",
        account_id="ACC-STUDENT-001",
        category="Food",
        budget_remaining=300.00
    )
