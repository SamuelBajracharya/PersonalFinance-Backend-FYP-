# train_and_tune_param.py
import pandas as pd
import numpy as np
import joblib
import warnings
import tensorflow as tf

from sklearn.preprocessing import MinMaxScaler
from sklearn.model_selection import TimeSeriesSplit, GridSearchCV
from tensorflow.keras.models import Sequential
from tensorflow.keras.layers import LSTM, Dense
from xgboost import XGBClassifier

warnings.filterwarnings("ignore")


def train_models(
    transactions_file: str,
    prediction_category: str,
    look_back: int = 30,
    prediction_days: int = 1,
):
    df = pd.read_csv(transactions_file)
    df["date"] = pd.to_datetime(df["date"]).dt.date
    df["amount"] = pd.to_numeric(df["amount"], errors="coerce")
    df.dropna(subset=["amount"], inplace=True)

    daily_spend = (
        df.groupby(["account_id", "date", "category"])["amount"].sum().reset_index()
    )

    category_data = daily_spend[daily_spend["category"] == prediction_category]

    if category_data.empty:
        raise ValueError("No data for this category")

    lstm_input = category_data.pivot(
        index="date", columns="account_id", values="amount"
    ).fillna(0)

    full_dates = pd.date_range(lstm_input.index.min(), lstm_input.index.max(), freq="D")

    lstm_input = lstm_input.reindex(full_dates).fillna(0)
    lstm_input.index = lstm_input.index.date

    scaler = MinMaxScaler()
    scaled_data = scaler.fit_transform(lstm_input)

    def create_dataset(data):
        X, Y = [], []
        for i in range(len(data) - look_back - prediction_days + 1):
            X.append(data[i : i + look_back])
            Y.append(data[i + look_back : i + look_back + prediction_days].mean(axis=1))
        return np.array(X), np.array(Y)

    X, Y = create_dataset(scaled_data)
    Y = Y.reshape(-1, prediction_days)

    split = int(len(X) * 0.9)
    X_train, Y_train = X[:split], Y[:split]

    model = Sequential(
        [LSTM(96, input_shape=(X_train.shape[1], X_train.shape[2])), Dense(1)]
    )

    model.compile(optimizer=tf.keras.optimizers.Adam(0.001), loss="mse")

    model.fit(X_train, Y_train, epochs=15, batch_size=16, shuffle=False, verbose=1)

    lstm_preds_scaled = model.predict(X, verbose=0)
    lstm_preds = scaler.inverse_transform(
        np.repeat(lstm_preds_scaled, lstm_input.shape[1], axis=1)
    ).mean(axis=1)

    prediction_dates = lstm_input.index[look_back : look_back + len(lstm_preds)]
    lstm_series = pd.Series(lstm_preds, index=prediction_dates)

    target_series = lstm_input.mean(axis=1)

    xgb_df = pd.DataFrame(index=lstm_input.index)
    xgb_df["day_of_week"] = pd.to_datetime(xgb_df.index).dayofweek
    xgb_df["rolling_7_mean"] = target_series.rolling(7).mean()
    xgb_df["rolling_7_std"] = target_series.rolling(7).std()
    xgb_df["lstm_predicted"] = lstm_series
    xgb_df["actual_amount"] = target_series

    xgb_df["risk_label"] = (
        xgb_df["actual_amount"]
        > (xgb_df["rolling_7_mean"] + xgb_df["rolling_7_std"].fillna(0) * 0.5)
    ).astype(int)

    xgb_df.dropna(inplace=True)

    X_xgb = xgb_df.drop(columns=["actual_amount", "risk_label"])
    Y_xgb = xgb_df["risk_label"]

    if Y_xgb.nunique() <= 1:
        dummy_X = X_xgb.iloc[[-1]]
        dummy_Y = pd.Series([1 - Y_xgb.iloc[0]], index=dummy_X.index)
        X_xgb = pd.concat([X_xgb, dummy_X])
        Y_xgb = pd.concat([Y_xgb, dummy_Y])

        xgb_model = XGBClassifier(
            objective="binary:logistic",
            eval_metric="logloss",
            random_state=42,
            n_estimators=50,
        )
        xgb_model.fit(X_xgb, Y_xgb)
    else:
        tscv = TimeSeriesSplit(3)
        grid = GridSearchCV(
            XGBClassifier(
                objective="binary:logistic", eval_metric="logloss", random_state=42
            ),
            {
                "n_estimators": [50, 100],
                "max_depth": [3, 4],
                "learning_rate": [0.1, 0.05],
            },
            cv=tscv,
            scoring="f1",
            n_jobs=-1,
        )
        grid.fit(X_xgb, Y_xgb)
        xgb_model = grid.best_estimator_

    prefix = f"GLOBAL_{prediction_category}"

    model.save(f"lstm_{prefix}.keras")
    joblib.dump(xgb_model, f"xgb_{prefix}.pkl")
    joblib.dump(scaler, f"scaler_{prefix}.pkl")
    joblib.dump(lstm_input.columns, f"accounts_{prefix}.pkl")


if __name__ == "__main__":
    train_models(
        transactions_file="transactions.csv",
        prediction_category="Shopping",
        look_back=30,
    )
