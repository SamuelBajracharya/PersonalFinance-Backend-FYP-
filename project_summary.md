# Project Summary

This document provides a comprehensive overview of the personal finance management application.

## Core Features

The application is built with FastAPI and includes the following core features:

*   **User Authentication:** Standard email/password authentication with JWT tokens.
*   **Bank Synchronization:** Syncs bank accounts and transactions from an external provider.
*   **Budget Management:** Allows users to set and track budgets for different spending categories.
*   **Gamified Rewards:** A system of XP and ranks to incentivize financial goals.
*   **AI-Powered Insights:** Provides daily spending predictions and risk analysis.
*   **Financial Analytics:** Detailed analytics and visualizations of financial data.
*   **AI Advisor:** Personalized financial advice through a chat-like interface.
*   **What-If Scenarios:** Explores potential savings based on spending habits.

## Project Structure

The project is organized into several key directories:

*   `main.py`: The main entry point for the FastAPI application.
*   `app/`: Contains the core application logic, separated into `api`, `crud`, `models`, `schemas`, and `services`.
*   `ai/`: Contains the machine learning models and inference logic.
*   `alembic/`: Manages database migrations.

## Detailed Feature Flows

### 1. User Authentication

This feature manages user registration, login, and secure access to the application using a multi-step OTP (One-Time Password) process.

*   **Models:** `app/models/user.py` (`User`), `app/models/otp.py` (`OTP`)
*   **API Router:** `app/api/auth.py`

**Flow:**
1.  **Registration:** A new user signs up using the `POST /api/v1/auth/create` endpoint. The system creates a `User` record with an unverified status and returns a temporary token.
2.  **Request OTP:** The user then calls `POST /api/v1/auth/request-otp` with the temporary token and a purpose (e.g., `ACCOUNT_VERIFICATION`). The backend generates an OTP, saves it, and emails it to the user.
3.  **Verification:** The user submits the OTP to `POST /api/v1/auth/verify-otp`. If valid, the user's account is marked as verified, and the endpoint returns a full `access_token` and `refresh_token`.
4.  **Login:** For subsequent logins, the user calls `POST /api/v1/auth/login` to get a temporary token, requests an OTP for `TWO_FACTOR_AUTH`, and verifies it to get their access tokens.
5.  **Authenticated Access:** The access token is used to access protected endpoints like `GET /api/v1/auth/users/me`, which returns the current user's profile.
6.  **Password Reset:** A similar OTP flow is used for password resets, starting with `POST /api/v1/auth/request-password-reset` and completing with `POST /api/v1/auth/reset-password`.

### 2. Bank Account and Transaction Syncing

This feature connects to a user's bank via a third-party aggregator to automatically fetch and categorize financial data.

*   **Models:** `app/models/bank.py` (`BankAccount`, `Transaction`)
*   **API Router:** `app/api/bank.py`
*   **Service:** `app/services/bank_sync.py`

**Flow:**
1.  **Link Account:** The user provides their bank credentials to the `POST /api/v1/bank/bank-login` endpoint.
2.  **Sync Data:** The `bank_sync` service uses these credentials to connect to the financial data aggregator, fetches account and transaction data, and stores it in the `BankAccount` and `Transaction` tables. The `external_id` fields link the internal records to the aggregator's records.
3.  **View Accounts:** The user can list their linked accounts via `GET /api/v1/bank/accounts`.
4.  **Manage Data:** Users can unlink their accounts (deactivating them) with `POST /api/v1/bank/unlink` or delete all their transaction history with `DELETE /api/v1/bank/delete-data`.

### 3. Budgeting

This feature allows users to set monthly spending limits for various categories and track their progress.

*   **Model:** `app/models/budget.py` (`Budget`)
*   **API Router:** `app/api/budget.py`

**Flow:**
1.  **Create Budget:** A user defines a new budget by calling `POST /api/v1/budget/` with a `category` and `budget_amount`. The system creates a `Budget` record for the current 30-day period.
2.  **View Budgets:** Users can see all their active budgets with `GET /api/v1/budget/`. The frontend is expected to use this data to display progress bars by comparing spending (from `Transaction` data) against the `budget_amount`.
3.  **Update/Delete:** Budgets can be modified using `PUT /api/v1/budget/{budget_id}` or removed with `DELETE /api/v1/budget/{budget_id}`.

### 4. AI-Powered Daily Predictions

This feature uses machine learning to forecast a user's spending and assess their risk of going over budget.

*   **Model:** `app/models/daily_prediction.py` (`DailyPrediction`)
*   **API Router:** `app/api/ai_predictions.py`
*   **AI Logic:** `ai/inference.py`

**Flow:**
1.  **Trigger Prediction:** The client calls `GET /api/v1/ai-predictions/predict/budgets/`.
2.  **Generate & Store:** For each of the user's active budgets, the system invokes the `predict_next_day` function from `ai/inference.py`. This function loads pre-trained models, considers historical spending and remaining budget, and calculates a `predicted_amount` and a `risk_level`.
3.  **Save Output:** The results are stored in the `DailyPrediction` table for historical tracking.
4.  **Return to User:** The endpoint returns the newly generated predictions to the client to be displayed as a forecast.

### 5. Gamification and Rewards

This feature incentivizes good financial habits by awarding experience points (XP) and unlocking badges.

*   **Models:** `app/models/reward.py` (`Reward`, `UserReward`), `app/models/user.py` (`User`)
*   **API Router:** `app/api/rewards.py`
*   **Service:** `app/services/reward_evaluation.py`

**Flow:**
1.  **Evaluate Achievements:** Key actions, such as logging in or creating a budget, trigger the `evaluate_rewards` service. This service checks if the user's actions or profile stats (e.g., `total_xp`) meet the criteria for any defined `Reward`.
2.  **Unlock Rewards:** If a reward condition is met, a new entry is created in the `UserReward` table, linking the user to the `Reward`.
3.  **View Status:** The user can see all available rewards and their unlock status by calling `GET /api/v1/rewards/`.
4.  **View Unlocked:** A list of only the user's earned rewards is available at `GET /api/v1/rewards/me`.
5.  **Recent Activity:** A feed of the most recently unlocked rewards can be fetched from `GET /api/v1/rewards/recent-activity`.

### 6. Dashboard & Analytics

These features provide high-level summaries and detailed, filterable visualizations of the user's financial data.

*   **API Routers:** `app/api/dashboard.py`, `app/api/analytics.py`

**Flow:**
1.  **Dashboard Summary:** The frontend calls `GET /api/v1/dashboard/{external_id}` for a specific bank account. This endpoint calculates summary totals (income, expenses, balance) and generates simplified line charts for yearly, monthly, and weekly trends.
2.  **Detailed Analytics:** For a more in-depth view, the client calls `GET /api/v1/analytics/{external_id}`. This endpoint performs more complex data aggregation using `pandas` to generate:
    *   Bar charts for transactions and balances (yearly, monthly, weekly).
    *   Dual-line series charts comparing income vs. expenses.
    *   Pie charts showing the top 5 expense and income categories.

### 7. AI Advisor & What-If Scenarios

These features provide proactive, AI-driven financial guidance.

*   **API Routers:** `app/api/ai_advisor.py`, `app/api/what_if_scenarios.py`
*   **Services:** `app/services/ai_advisor.py`, `app/services/what_if_scenarios.py`

**Flow:**
1.  **AI Advisor:** The user sends a question or prompt (e.g., "How can I save more money?") to `POST /api/v1/ai-advisor/advisor`. The `generate_advice` service processes this prompt along with the user's financial data to generate a personalized response.
2.  **What-If Scenarios:** The client calls `GET /api/v1/what-if-scenarios/`. The backend service analyzes the current month's spending and identifies categories where small reductions (e.g., 10%, 15%) could lead to significant savings, returning these as actionable scenarios.