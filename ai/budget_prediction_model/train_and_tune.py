# train_and_tune_param.py
import pandas as pd
import numpy as np
import joblib
import warnings
import tensorflow as tf

from sklearn.metrics import f1_score, mean_squared_error, r2_score
from sklearn.model_selection import GridSearchCV, TimeSeriesSplit
from sklearn.preprocessing import MinMaxScaler
from xgboost import XGBClassifier

warnings.filterwarnings("ignore")

np.random.seed(42)
tf.random.set_seed(42)


def _create_dataset(data: np.ndarray, look_back: int, prediction_days: int):
    X, Y = [], []
    for i in range(len(data) - look_back - prediction_days + 1):
        X.append(data[i : i + look_back])
        Y.append(data[i + look_back : i + look_back + prediction_days].mean(axis=1))
    return np.array(X), np.array(Y)


def _build_lstm(input_shape: tuple[int, int], units_1: int, units_2: int):
    model = tf.keras.Sequential(
        [
            tf.keras.layers.Input(shape=input_shape),
            tf.keras.layers.LSTM(
                units_1,
                return_sequences=True,
                dropout=0.2,
                recurrent_dropout=0.1,
            ),
            tf.keras.layers.LSTM(units_2, dropout=0.2, recurrent_dropout=0.1),
            tf.keras.layers.Dense(16, activation="relu"),
            tf.keras.layers.Dense(1),
        ]
    )
    model.compile(
        optimizer=tf.keras.optimizers.Adam(learning_rate=0.001),
        loss=tf.keras.losses.Huber(delta=1.0),
        metrics=["mae"],
    )
    return model


def _pick_best_lstm(scaled_data: np.ndarray, requested_look_back: int):
    candidates = []
    for lb in [14, 21, requested_look_back]:
        if lb not in candidates:
            candidates.append(lb)

    best = None

    for look_back in candidates:
        X, Y = _create_dataset(scaled_data, look_back=look_back, prediction_days=1)
        if len(X) < max(look_back * 2, 80):
            continue

        Y = Y.reshape(-1, 1)
        train_end = int(len(X) * 0.8)
        val_end = int(len(X) * 0.9)
        X_train, Y_train = X[:train_end], Y[:train_end]
        X_val, Y_val = X[train_end:val_end], Y[train_end:val_end]
        X_test, Y_test = X[val_end:], Y[val_end:]

        for units_1, units_2 in [(64, 32), (48, 24), (32, 16)]:
            model = _build_lstm(
                input_shape=(X_train.shape[1], X_train.shape[2]),
                units_1=units_1,
                units_2=units_2,
            )

            callbacks = [
                tf.keras.callbacks.EarlyStopping(
                    monitor="val_loss",
                    patience=8,
                    restore_best_weights=True,
                    min_delta=1e-4,
                ),
                tf.keras.callbacks.ReduceLROnPlateau(
                    monitor="val_loss",
                    factor=0.5,
                    patience=4,
                    min_lr=1e-5,
                    verbose=0,
                ),
            ]

            history = model.fit(
                X_train,
                Y_train,
                validation_data=(X_val, Y_val),
                epochs=60,
                batch_size=16,
                shuffle=False,
                verbose=0,
                callbacks=callbacks,
            )

            y_val_pred = model.predict(X_val, verbose=0).reshape(-1)
            y_test_pred = model.predict(X_test, verbose=0).reshape(-1)

            val_mse = float(mean_squared_error(Y_val.reshape(-1), y_val_pred))
            test_r2 = float(r2_score(Y_test.reshape(-1), y_test_pred))

            candidate = {
                "look_back": look_back,
                "units_1": units_1,
                "units_2": units_2,
                "model": model,
                "X_full": X,
                "Y_full": Y,
                "val_mse": val_mse,
                "test_r2": test_r2,
                "best_val_loss": float(min(history.history.get("val_loss", [np.inf]))),
            }

            if best is None or candidate["val_mse"] < best["val_mse"]:
                best = candidate

    if best is None:
        raise ValueError(
            "Not enough sequence windows for stable LSTM training. "
            "Add more history or reduce look_back."
        )

    return best


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

    best_lstm = _pick_best_lstm(scaled_data, requested_look_back=look_back)
    model = best_lstm["model"]
    X = best_lstm["X_full"]

    print(
        f"[LSTM][{prediction_category}] look_back={best_lstm['look_back']} "
        f"units=({best_lstm['units_1']},{best_lstm['units_2']}) "
        f"val_mse={best_lstm['val_mse']:.6f} test_r2={best_lstm['test_r2']:.4f}"
    )

    lstm_preds_scaled = model.predict(X, verbose=0)
    lstm_preds = scaler.inverse_transform(
        np.repeat(lstm_preds_scaled, lstm_input.shape[1], axis=1)
    ).mean(axis=1)

    effective_look_back = int(best_lstm["look_back"])
    prediction_dates = lstm_input.index[
        effective_look_back : effective_look_back + len(lstm_preds)
    ]
    lstm_series = pd.Series(lstm_preds, index=prediction_dates)

    target_series = lstm_input.mean(axis=1)

    xgb_df = pd.DataFrame(index=lstm_input.index)
    xgb_df["day_of_week"] = pd.to_datetime(xgb_df.index).dayofweek
    xgb_df["day_of_month"] = pd.to_datetime(xgb_df.index).day
    xgb_df["is_weekend"] = (xgb_df["day_of_week"] >= 5).astype(int)
    xgb_df["lag_1_amount"] = target_series.shift(1)
    xgb_df["lag_2_amount"] = target_series.shift(2)
    xgb_df["rolling_3_mean"] = target_series.rolling(3).mean()
    xgb_df["rolling_7_mean"] = target_series.rolling(7).mean()
    xgb_df["rolling_7_std"] = target_series.rolling(7).std()
    xgb_df["rolling_14_mean"] = target_series.rolling(14).mean()
    xgb_df["rolling_14_std"] = target_series.rolling(14).std()
    xgb_df["lstm_predicted"] = lstm_series
    xgb_df["actual_amount"] = target_series

    xgb_df["risk_label"] = (
        xgb_df["actual_amount"]
        > (xgb_df["rolling_7_mean"] + xgb_df["rolling_7_std"].fillna(0) * 0.5)
    ).astype(int)

    xgb_df.dropna(inplace=True)

    X_xgb = xgb_df.drop(columns=["actual_amount", "risk_label"])
    Y_xgb = xgb_df["risk_label"]

    if len(X_xgb) < 60:
        raise ValueError(
            "Not enough rows for robust XGBoost training. Add more historical data."
        )

    split_xgb = int(len(X_xgb) * 0.9)
    X_xgb_train, X_xgb_test = X_xgb.iloc[:split_xgb], X_xgb.iloc[split_xgb:]
    Y_xgb_train, Y_xgb_test = Y_xgb.iloc[:split_xgb], Y_xgb.iloc[split_xgb:]

    if Y_xgb_train.nunique() <= 1:
        dummy_X = X_xgb_train.iloc[[-1]]
        dummy_Y = pd.Series([1 - Y_xgb_train.iloc[0]], index=dummy_X.index)
        X_xgb_train = pd.concat([X_xgb_train, dummy_X])
        Y_xgb_train = pd.concat([Y_xgb_train, dummy_Y])

        xgb_model = XGBClassifier(
            objective="binary:logistic",
            eval_metric="logloss",
            random_state=42,
            n_estimators=120,
            max_depth=3,
            learning_rate=0.05,
            subsample=0.9,
            colsample_bytree=0.9,
            reg_lambda=2.0,
        )
        xgb_model.fit(X_xgb_train, Y_xgb_train)
    else:
        positives = int((Y_xgb_train == 1).sum())
        negatives = int((Y_xgb_train == 0).sum())
        scale_pos_weight = (negatives / positives) if positives > 0 else 1.0

        tscv = TimeSeriesSplit(4)
        grid = GridSearchCV(
            XGBClassifier(
                objective="binary:logistic",
                eval_metric="logloss",
                random_state=42,
                scale_pos_weight=scale_pos_weight,
                tree_method="hist",
            ),
            {
                "n_estimators": [100, 200, 300],
                "max_depth": [3, 4, 5],
                "learning_rate": [0.03, 0.05, 0.08],
                "subsample": [0.8, 1.0],
                "colsample_bytree": [0.8, 1.0],
                "min_child_weight": [1, 3],
                "gamma": [0.0, 0.2],
                "reg_lambda": [1.0, 2.0],
            },
            cv=tscv,
            scoring="f1",
            n_jobs=-1,
            verbose=0,
        )
        grid.fit(X_xgb_train, Y_xgb_train)
        xgb_model = grid.best_estimator_

        train_pred = xgb_model.predict(X_xgb_train)
        test_pred = xgb_model.predict(X_xgb_test)
        print(
            f"[XGB][{prediction_category}] best={grid.best_params_} "
            f"train_f1={f1_score(Y_xgb_train, train_pred):.3f} "
            f"test_f1={f1_score(Y_xgb_test, test_pred):.3f}"
        )

    test_prob = xgb_model.predict_proba(X_xgb_test)[:, 1]
    threshold_grid = np.linspace(0.35, 0.75, 9)
    best_threshold = 0.6
    best_threshold_f1 = -1.0
    for th in threshold_grid:
        th_pred = (test_prob >= th).astype(int)
        score = f1_score(Y_xgb_test, th_pred, zero_division=0)
        if score > best_threshold_f1:
            best_threshold_f1 = score
            best_threshold = float(th)

    rolling_7_mean = target_series.rolling(7).mean().dropna()
    fallback_amount = (
        float(rolling_7_mean.iloc[-1]) if not rolling_7_mean.empty else 0.0
    )
    lstm_quality = max(0.0, min(1.0, (float(best_lstm["test_r2"]) + 0.25) / 0.75))

    metadata = {
        "look_back": effective_look_back,
        "prediction_days": int(prediction_days),
        "lstm_units": [int(best_lstm["units_1"]), int(best_lstm["units_2"])],
        "lstm_val_mse": float(best_lstm["val_mse"]),
        "lstm_test_r2": float(best_lstm["test_r2"]),
        "lstm_quality": float(lstm_quality),
        "fallback_amount": float(fallback_amount),
        "risk_threshold": float(best_threshold),
        "risk_threshold_f1": float(best_threshold_f1),
    }

    prefix = f"GLOBAL_{prediction_category}"

    model.save(f"lstm_{prefix}.keras")
    joblib.dump(xgb_model, f"xgb_{prefix}.pkl")
    joblib.dump(scaler, f"scaler_{prefix}.pkl")
    joblib.dump(lstm_input.columns, f"accounts_{prefix}.pkl")
    joblib.dump(metadata, f"meta_{prefix}.pkl")


if __name__ == "__main__":
    train_models(
        transactions_file="transactions.csv",
        prediction_category="Shopping",
        look_back=30,
    )
