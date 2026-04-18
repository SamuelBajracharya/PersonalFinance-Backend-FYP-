import pandas as pd
import numpy as np
import joblib
import warnings
import tensorflow as tf
import re

from sklearn.metrics import accuracy_score, f1_score, mean_absolute_error, r2_score
from sklearn.model_selection import GridSearchCV, TimeSeriesSplit
from sklearn.preprocessing import MinMaxScaler
from xgboost import XGBClassifier

warnings.filterwarnings("ignore")

np.random.seed(42)
tf.random.set_seed(42)


XGB_FEATURE_COLUMNS = [
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
]


def _build_category_daily_series(df: pd.DataFrame, prediction_category: str):
    daily_spend = (
        df.groupby(["account_id", "date", "category"])["amount"].sum().reset_index()
    )
    category_data = daily_spend[daily_spend["category"] == prediction_category].copy()
    if category_data.empty:
        raise ValueError(f"No data for category '{prediction_category}'")

    panel = category_data.pivot(
        index="date", columns="account_id", values="amount"
    ).fillna(0)
    full_dates = pd.date_range(panel.index.min(), panel.index.max(), freq="D")
    panel = panel.reindex(full_dates).fillna(0)

    # Global category behavior across users/accounts.
    daily_series = panel.mean(axis=1).astype(float)
    return daily_series, panel.columns.astype(str)


def _category_model_key(category: str) -> str:
    key = re.sub(r"[^A-Za-z0-9]+", "_", str(category).strip())
    key = re.sub(r"_+", "_", key).strip("_")
    return key or "Uncategorized"


def _create_sequence_dataset(series_scaled: np.ndarray, look_back: int):
    X, y = [], []
    for i in range(look_back, len(series_scaled)):
        X.append(series_scaled[i - look_back : i])
        y.append(series_scaled[i])
    return np.array(X), np.array(y)


def _build_lstm_model(input_shape: tuple[int, int], units_1: int, units_2: int):
    model = tf.keras.Sequential(
        [
            tf.keras.layers.Input(shape=input_shape),
            tf.keras.layers.LSTM(
                units_1,
                return_sequences=True,
                dropout=0.15,
                recurrent_dropout=0.05,
            ),
            tf.keras.layers.LSTM(units_2, dropout=0.15, recurrent_dropout=0.05),
            tf.keras.layers.Dense(24, activation="relu"),
            tf.keras.layers.Dense(1),
        ]
    )
    model.compile(
        optimizer=tf.keras.optimizers.Adam(learning_rate=1e-3),
        loss=tf.keras.losses.Huber(delta=1.0),
        metrics=["mae"],
    )
    return model


def _fit_best_lstm(series: pd.Series, look_back: int):
    if len(series) < max(120, look_back + 40):
        raise ValueError("Not enough category history for reliable LSTM training")

    split_idx = int(len(series) * 0.8)
    train_series = series.iloc[:split_idx]

    scaler = MinMaxScaler()
    scaler.fit(train_series.to_numpy().reshape(-1, 1))
    scaled_full = scaler.transform(series.to_numpy().reshape(-1, 1)).reshape(-1)

    X, y = _create_sequence_dataset(scaled_full, look_back=look_back)
    if len(X) < 80:
        raise ValueError("Not enough sequence windows after look_back")

    train_end = int(len(X) * 0.7)
    val_end = int(len(X) * 0.85)

    X_train, y_train = X[:train_end], y[:train_end]
    X_val, y_val = X[train_end:val_end], y[train_end:val_end]
    X_test, y_test = X[val_end:], y[val_end:]

    # Keras expects [samples, timesteps, features].
    X_train = X_train.reshape((-1, look_back, 1))
    X_val = X_val.reshape((-1, look_back, 1))
    X_test = X_test.reshape((-1, look_back, 1))

    best = None
    for units_1, units_2 in [(64, 32), (48, 24), (32, 16)]:
        model = _build_lstm_model(
            input_shape=(look_back, 1),
            units_1=units_1,
            units_2=units_2,
        )

        callbacks = [
            tf.keras.callbacks.EarlyStopping(
                monitor="val_loss",
                patience=10,
                restore_best_weights=True,
                min_delta=1e-4,
            ),
            tf.keras.callbacks.ReduceLROnPlateau(
                monitor="val_loss",
                factor=0.5,
                patience=5,
                min_lr=1e-5,
                verbose=0,
            ),
        ]

        history = model.fit(
            X_train,
            y_train,
            validation_data=(X_val, y_val),
            epochs=120,
            batch_size=16,
            shuffle=False,
            verbose=0,
            callbacks=callbacks,
        )

        val_pred = model.predict(X_val, verbose=0).reshape(-1)
        test_pred = model.predict(X_test, verbose=0).reshape(-1)

        val_mae = float(mean_absolute_error(y_val, val_pred))
        test_r2_scaled = float(r2_score(y_test, test_pred))

        y_test_inv = scaler.inverse_transform(y_test.reshape(-1, 1)).reshape(-1)
        test_pred_inv = scaler.inverse_transform(test_pred.reshape(-1, 1)).reshape(-1)
        test_r2_original = float(r2_score(y_test_inv, test_pred_inv))

        candidate = {
            "model": model,
            "units_1": units_1,
            "units_2": units_2,
            "val_mae": val_mae,
            "test_r2_scaled": test_r2_scaled,
            "test_r2_original": test_r2_original,
            "best_val_loss": float(min(history.history.get("val_loss", [np.inf]))),
            "scaled_full": scaled_full,
            "train_end": train_end,
            "val_end": val_end,
            "x_all": X.reshape((-1, look_back, 1)),
            "y_all": y,
        }
        if best is None or candidate["val_mae"] < best["val_mae"]:
            best = candidate

    if best is None:
        raise ValueError("LSTM model search failed")

    return best, scaler


def _build_xgb_dataset(series: pd.Series, lstm_pred_series: pd.Series):
    df = pd.DataFrame(index=series.index)
    df["actual_amount"] = series.astype(float)

    # Feature set based only on past values at time t for predicting t+1.
    df["day_of_week"] = pd.to_datetime(df.index).dayofweek
    df["day_of_month"] = pd.to_datetime(df.index).day
    df["is_weekend"] = (df["day_of_week"] >= 5).astype(int)

    df["lag_1_amount"] = df["actual_amount"].shift(1)
    df["lag_2_amount"] = df["actual_amount"].shift(2)
    df["lag_3_amount"] = df["actual_amount"].shift(3)

    df["rolling_3_mean"] = df["actual_amount"].shift(1).rolling(3).mean()
    df["rolling_7_mean"] = df["actual_amount"].shift(1).rolling(7).mean()
    df["rolling_14_mean"] = df["actual_amount"].shift(1).rolling(14).mean()
    df["rolling_7_std"] = df["actual_amount"].shift(1).rolling(7).std()
    df["rolling_14_std"] = df["actual_amount"].shift(1).rolling(14).std()
    df["trend_7"] = df["actual_amount"].shift(1) - df["actual_amount"].shift(8)

    df["lstm_predicted"] = lstm_pred_series.reindex(df.index)

    df["target_next_amount"] = df["actual_amount"].shift(-1)
    threshold = df["rolling_7_mean"] + 0.5 * df["rolling_7_std"].fillna(0)
    df["risk_label"] = (df["target_next_amount"] > threshold).astype(int)

    df = df.dropna().copy()
    X = df[XGB_FEATURE_COLUMNS]
    y = df["risk_label"].astype(int)
    return X, y


def _fit_xgb(X: pd.DataFrame, y: pd.Series):
    if len(X) < 100:
        raise ValueError("Not enough rows for robust XGBoost training")

    train_end = int(len(X) * 0.7)
    val_end = int(len(X) * 0.85)

    X_train, y_train = X.iloc[:train_end], y.iloc[:train_end]
    X_val, y_val = X.iloc[train_end:val_end], y.iloc[train_end:val_end]
    X_test, y_test = X.iloc[val_end:], y.iloc[val_end:]

    if y_train.nunique() <= 1:
        fallback = XGBClassifier(
            objective="binary:logistic",
            eval_metric="logloss",
            random_state=42,
            n_estimators=200,
            max_depth=3,
            learning_rate=0.05,
            subsample=0.9,
            colsample_bytree=0.9,
        )
        fallback.fit(X_train, y_train)
        best_model = fallback
    else:
        positives = int((y_train == 1).sum())
        negatives = int((y_train == 0).sum())
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
                "n_estimators": [150, 250, 350],
                "max_depth": [3, 4, 5],
                "learning_rate": [0.02, 0.05],
                "subsample": [0.8, 1.0],
                "colsample_bytree": [0.8, 1.0],
                "min_child_weight": [1, 3],
                "gamma": [0.0, 0.15],
                "reg_lambda": [1.0, 2.0],
            },
            cv=tscv,
            scoring="f1",
            n_jobs=-1,
            verbose=0,
        )
        grid.fit(X_train, y_train)
        best_model = grid.best_estimator_

    val_prob = best_model.predict_proba(X_val)[:, 1]
    threshold_grid = np.linspace(0.35, 0.75, 9)
    best_threshold = 0.5
    best_threshold_f1 = -1.0
    for threshold in threshold_grid:
        pred = (val_prob >= threshold).astype(int)
        score = f1_score(y_val, pred, zero_division=0)
        if score > best_threshold_f1:
            best_threshold_f1 = float(score)
            best_threshold = float(threshold)

    test_prob = best_model.predict_proba(X_test)[:, 1]
    test_pred = (test_prob >= best_threshold).astype(int)

    metrics = {
        "xgb_test_accuracy": float(accuracy_score(y_test, test_pred)),
        "xgb_test_f1": float(f1_score(y_test, test_pred, zero_division=0)),
        "risk_threshold": best_threshold,
        "risk_threshold_f1": best_threshold_f1,
    }
    return best_model, metrics


def train_models(
    transactions_file: str,
    prediction_category: str,
    look_back: int = 30,
):
    df = pd.read_csv(transactions_file)
    df["date"] = pd.to_datetime(df["date"]).dt.date
    df["amount"] = pd.to_numeric(df["amount"], errors="coerce")
    df = df.dropna(subset=["amount"]).copy()

    daily_series, account_columns = _build_category_daily_series(
        df, prediction_category
    )

    best_lstm, scaler = _fit_best_lstm(daily_series, look_back=look_back)
    lstm_model = best_lstm["model"]

    lstm_pred_scaled_all = lstm_model.predict(best_lstm["x_all"], verbose=0).reshape(-1)
    lstm_pred_all = scaler.inverse_transform(
        lstm_pred_scaled_all.reshape(-1, 1)
    ).reshape(-1)
    lstm_pred_series = pd.Series(lstm_pred_all, index=daily_series.index[look_back:])

    X_xgb, y_xgb = _build_xgb_dataset(daily_series, lstm_pred_series)
    xgb_model, xgb_metrics = _fit_xgb(X_xgb, y_xgb)

    fallback_amount = (
        float(daily_series.tail(7).mean())
        if len(daily_series) >= 7
        else float(daily_series.mean())
    )
    lstm_quality = max(0.0, min(1.0, (best_lstm["test_r2_original"] + 0.25) / 0.75))

    print(
        f"[LSTM][{prediction_category}] units=({best_lstm['units_1']},{best_lstm['units_2']}) "
        f"val_mae={best_lstm['val_mae']:.6f} "
        f"test_r2_scaled={best_lstm['test_r2_scaled']:.4f} "
        f"test_r2_original={best_lstm['test_r2_original']:.4f}"
    )
    print(
        f"[XGB][{prediction_category}] test_acc={xgb_metrics['xgb_test_accuracy']:.4f} "
        f"test_f1={xgb_metrics['xgb_test_f1']:.4f} "
        f"thr={xgb_metrics['risk_threshold']:.2f}"
    )

    metadata = {
        "look_back": int(look_back),
        "lstm_units": [int(best_lstm["units_1"]), int(best_lstm["units_2"])],
        "lstm_val_mae": float(best_lstm["val_mae"]),
        "lstm_test_r2_scaled": float(best_lstm["test_r2_scaled"]),
        "lstm_test_r2": float(best_lstm["test_r2_original"]),
        "lstm_quality": float(lstm_quality),
        "fallback_amount": float(fallback_amount),
        "risk_threshold": float(xgb_metrics["risk_threshold"]),
        "risk_threshold_f1": float(xgb_metrics["risk_threshold_f1"]),
        "xgb_test_accuracy": float(xgb_metrics["xgb_test_accuracy"]),
        "xgb_test_f1": float(xgb_metrics["xgb_test_f1"]),
        "xgb_feature_columns": XGB_FEATURE_COLUMNS,
    }

    category_model_key = _category_model_key(prediction_category)
    prefix = f"GLOBAL_{category_model_key}"
    lstm_model.save(f"lstm_{prefix}.keras")
    joblib.dump(xgb_model, f"xgb_{prefix}.pkl")
    joblib.dump(scaler, f"scaler_{prefix}.pkl")
    joblib.dump(account_columns.tolist(), f"accounts_{prefix}.pkl")
    metadata["category"] = str(prediction_category)
    metadata["category_model_key"] = category_model_key
    joblib.dump(metadata, f"meta_{prefix}.pkl")


def train_all_categories(
    transactions_file: str,
    look_back: int = 30,
    min_rows_per_category: int = 50,
):
    df = pd.read_csv(transactions_file)
    df["amount"] = pd.to_numeric(df["amount"], errors="coerce")
    df["category"] = df["category"].astype(str).str.strip()
    df = df.dropna(subset=["amount"]).copy()

    category_counts = (
        df[df["category"] != ""].groupby("category").size().sort_values(ascending=False)
    )
    categories = [
        c for c, n in category_counts.items() if int(n) >= int(min_rows_per_category)
    ]

    if not categories:
        raise ValueError("No categories meet min_rows_per_category for training")

    outcomes: list[dict] = []
    for category in categories:
        try:
            train_models(
                transactions_file=transactions_file,
                prediction_category=category,
                look_back=look_back,
            )
            outcomes.append({"category": category, "status": "trained"})
        except Exception as exc:
            outcomes.append(
                {"category": category, "status": "failed", "error": str(exc)}
            )

    trained_count = sum(1 for item in outcomes if item["status"] == "trained")
    print(f"[TRAIN_ALL] trained={trained_count} failed={len(outcomes) - trained_count}")
    for item in outcomes:
        if item["status"] != "trained":
            print(
                f"[TRAIN_ALL][FAILED] {item['category']}: {item.get('error', 'unknown')}"
            )

    return outcomes


if __name__ == "__main__":
    train_all_categories(
        transactions_file="transactions.csv",
        look_back=30,
        min_rows_per_category=50,
    )
