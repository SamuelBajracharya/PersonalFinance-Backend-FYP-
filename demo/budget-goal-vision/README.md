# Budget Goal Intelligence Vision Demo

This folder contains a lightweight frontend demo that showcases your new budget-goal intelligence APIs.

## Files
- index.html
- styles.css
- app.js

## What this demo uses
- GET /api/v1/budgets/goal-status
- GET /api/v1/budgets/{budget_id}/goal-status
- GET /api/v1/budgets/{budget_id}/prediction-explanation
- POST /api/v1/budgets/{budget_id}/simulate
- GET /api/v1/budgets/{budget_id}/suggestions
- GET /api/v1/budgets/{budget_id}/adaptive-adjustment
- GET /api/v1/budgets/{budget_id}/review

## Run
1. Start backend (FastAPI) on http://127.0.0.1:8000.
2. Serve this folder on a local HTTP server (not file://).
   - Example:
     - Python: python -m http.server 3000
3. Open http://127.0.0.1:3000/demo/budget-goal-vision/ (if serving from backend root), or open the direct folder root URL where index.html is hosted.
4. Paste a valid JWT access token in the page.
5. Click Refresh All.

## Notes
- CORS in your backend currently allows localhost:3000 and 127.0.0.1:3000, so serve this page from one of those origins.
- If no budgets exist, create budgets first and ensure there are transactions/predictions for richer output.
