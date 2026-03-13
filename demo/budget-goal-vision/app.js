const state = {
  statuses: [],
  selectedBudgetId: null,
  lastSimulation: null,
};

const refs = {
  baseUrl: document.getElementById("baseUrl"),
  token: document.getElementById("token"),
  refreshAllBtn: document.getElementById("refreshAllBtn"),
  statusCards: document.getElementById("statusCards"),
  statusEmpty: document.getElementById("statusEmpty"),
  statusCount: document.getElementById("statusCount"),
  selectedBudgetBadge: document.getElementById("selectedBudgetBadge"),
  globalMessage: document.getElementById("globalMessage"),
  heroInsight: document.getElementById("heroInsight"),
  pacePrediction: document.getElementById("pacePrediction"),
  simReduction: document.getElementById("simReduction"),
  simAbsolute: document.getElementById("simAbsolute"),
  runSimBtn: document.getElementById("runSimBtn"),
  simulationResult: document.getElementById("simulationResult"),
  suggestionsBlock: document.getElementById("suggestionsBlock"),
  adaptiveBlock: document.getElementById("adaptiveBlock"),
  chartBlock: document.getElementById("chartBlock"),
  reviewBlock: document.getElementById("reviewBlock"),
};

function setMessage(message) {
  refs.globalMessage.textContent = message;
}

function authHeaders() {
  const token = refs.token.value.trim();
  const headers = { "Content-Type": "application/json" };
  if (token) {
    headers.Authorization = `Bearer ${token}`;
  }
  return headers;
}

async function apiGet(path) {
  const response = await fetch(`${refs.baseUrl.value.trim()}${path}`, {
    method: "GET",
    headers: authHeaders(),
  });

  if (!response.ok) {
    const text = await response.text();
    throw new Error(`GET ${path} failed (${response.status}): ${text}`);
  }
  return response.json();
}

async function apiPost(path, payload) {
  const response = await fetch(`${refs.baseUrl.value.trim()}${path}`, {
    method: "POST",
    headers: authHeaders(),
    body: JSON.stringify(payload),
  });

  if (!response.ok) {
    const text = await response.text();
    throw new Error(`POST ${path} failed (${response.status}): ${text}`);
  }
  return response.json();
}

function toCurrency(value) {
  return `Rs ${Number(value || 0).toLocaleString()}`;
}

function toPercent(value) {
  return `${Number(value || 0).toFixed(1)}%`;
}

function renderKV(container, kvPairs) {
  container.innerHTML = kvPairs
    .map(
      ([key, value]) => `
      <div class="kv-item">
        <span class="k">${key}</span>
        <span class="v">${value}</span>
      </div>
    `
    )
    .join("");
}

function cardTemplate(status) {
  const progress = Math.max(0, Math.min(100, status.progress_percent || 0));
  const alerts = (status.alerts || [])
    .map(
      (a) =>
        `<span class="alert-chip alert-${(a.level || "medium").toLowerCase()}">${a.title}</span>`
    )
    .join("");

  const selectedClass = state.selectedBudgetId === status.budget_id ? "active" : "";

  return `
    <article class="card ${selectedClass}" data-budget-id="${status.budget_id}">
      <h3>${status.category}</h3>
      <div class="kpis">
        <div class="kpi"><div class="label">Current Spend</div><div class="value">${toCurrency(status.current_spend)}</div></div>
        <div class="kpi"><div class="label">Budget</div><div class="value">${toCurrency(status.budget_amount)}</div></div>
        <div class="kpi"><div class="label">Remaining</div><div class="value">${toCurrency(status.remaining_budget)}</div></div>
        <div class="kpi"><div class="label">Projected Spend</div><div class="value">${toCurrency(status.projected_period_spend)}</div></div>
      </div>
      <div class="progress-wrap">
        <div class="label">Progress ${toPercent(progress)}</div>
        <div class="progress-track"><div class="progress-fill" style="width: ${progress}%"></div></div>
      </div>
      <div class="kpis" style="margin-top: 8px;">
        <div class="kpi"><div class="label">Burn Rate / Day</div><div class="value">${toCurrency(status.burn_rate_per_day)}</div></div>
        <div class="kpi"><div class="label">Days Left</div><div class="value">${status.days_left}</div></div>
      </div>
      <div class="alerts">${alerts || '<span class="alert-chip alert-medium">No alerts</span>'}</div>
    </article>
  `;
}

function attachCardEvents() {
  const cards = refs.statusCards.querySelectorAll(".card");
  cards.forEach((card) => {
    card.addEventListener("click", async () => {
      const budgetId = card.getAttribute("data-budget-id");
      await selectBudget(budgetId);
    });
  });
}

function renderStatusCards() {
  refs.statusCount.textContent = `${state.statuses.length}`;
  refs.statusCards.innerHTML = state.statuses.map(cardTemplate).join("");

  if (!state.statuses.length) {
    refs.statusEmpty.classList.remove("hidden");
  } else {
    refs.statusEmpty.classList.add("hidden");
  }

  attachCardEvents();
}

function renderHeroAndPace(status) {
  const predictedOverrun = Math.max(
    0,
    Number(status.projected_period_spend || 0) - Number(status.budget_amount || 0)
  );
  const headline = status.predicted_to_exceed
    ? `Predicted overspend: ${toCurrency(predictedOverrun)}`
    : `On track with ${toCurrency(status.remaining_budget)} remaining`;

  refs.heroInsight.textContent = headline;

  const budgetAmount = Number(status.budget_amount || 1);
  const currentSpend = Number(status.current_spend || 0);
  const projectedSpend = Number(status.projected_period_spend || 0);
  const currentPct = Math.min(100, Math.max(0, (currentSpend / budgetAmount) * 100));
  const projectedPct = Math.min(
    100,
    Math.max(0, (projectedSpend / budgetAmount) * 100)
  );

  refs.pacePrediction.innerHTML = `
    <div class="kv-item"><span class="k">Predicted To Exceed</span><span class="v">${status.predicted_to_exceed ? "Yes" : "No"}</span></div>
    <div class="kv-item"><span class="k">Days Left</span><span class="v">${status.days_left}</span></div>
    <div class="kv-item"><span class="k">Current Spend</span><span class="v">${toCurrency(currentSpend)} / ${toCurrency(budgetAmount)}</span></div>
    <div class="progress-track" style="margin: 6px 0 12px;"><div class="progress-fill" style="width:${currentPct}%"></div></div>
    <div class="kv-item"><span class="k">AI Projected Spend</span><span class="v">${toCurrency(projectedSpend)} / ${toCurrency(budgetAmount)}</span></div>
    <div class="progress-track" style="margin-top: 6px;"><div class="progress-fill" style="width:${projectedPct}%"></div></div>
  `;
}

function renderChart(status, simulation = null) {
  const budget = Number(status.budget_amount || 0);
  const current = Number(status.current_spend || 0);
  const projected = Number(status.projected_period_spend || 0);
  const simulated = simulation
    ? Number(simulation.simulated_projected_spend || 0)
    : null;

  const maxValue = Math.max(budget, current, projected, simulated || 0, 1);

  const items = [
    { label: "Budget", value: budget, cls: "bar-budget" },
    { label: "Current", value: current, cls: "bar-current" },
    { label: "Projected", value: projected, cls: "bar-projected" },
  ];

  if (simulated !== null) {
    items.push({ label: "Simulated", value: simulated, cls: "bar-simulated" });
  }

  refs.chartBlock.innerHTML = `
    <div class="chart-grid">
      ${items
        .map((item) => {
          const pct = Math.max(2, (item.value / maxValue) * 100);
          return `
            <div class="chart-row">
              <div class="chart-label">${item.label}</div>
              <div class="chart-bar-track"><div class="chart-bar ${item.cls}" style="width:${pct}%"></div></div>
              <div class="chart-value">${toCurrency(item.value)}</div>
            </div>
          `;
        })
        .join("")}
    </div>
  `;
}

function renderSuggestions(data) {
  const html = (data.suggestions || [])
    .map(
      (s) => `
      <div class="list-item">
        <div class="title">${s.title} <span class="meta">(${s.priority})</span></div>
        <div>${s.message}</div>
        <div class="meta">Estimated savings: ${toCurrency(s.estimated_savings)}</div>
      </div>
    `
    )
    .join("");

  refs.suggestionsBlock.innerHTML = `<div class="list">${html || '<div class="empty">No suggestions right now.</div>'}</div>`;
}

function renderAdaptive(data) {
  renderKV(refs.adaptiveBlock, [
    ["Recommended Budget", toCurrency(data.recommended_budget_amount)],
    ["Adjustment %", toPercent(data.adjustment_percent)],
    ["Reason", data.reason],
  ]);
}

function renderReview(data) {
  renderKV(refs.reviewBlock, [
    ["Period", `${data.period_start} → ${data.period_end}`],
    ["Closed", data.is_period_closed ? "Yes" : "No"],
    ["Achieved", data.achieved ? "Yes" : "No"],
    ["Budget", toCurrency(data.budget_amount)],
    ["Total Spent", toCurrency(data.total_spent)],
    ["Savings / Overrun", toCurrency(data.savings_or_overrun)],
    ["Next Recommended", toCurrency(data.next_recommended_budget)],
    ["Summary", data.summary],
  ]);
}

function clearDetails() {
  refs.heroInsight.textContent = "Select a budget to load insight.";
  refs.pacePrediction.innerHTML = '<div class="empty">Select a budget to see pace and prediction.</div>';
  refs.suggestionsBlock.innerHTML = '<div class="empty">Select a budget to see suggestions.</div>';
  refs.adaptiveBlock.innerHTML = '<div class="empty">Select a budget to see adaptive target.</div>';
  refs.chartBlock.innerHTML = '<div class="empty">Run simulation or select a budget to see the chart.</div>';
  refs.reviewBlock.innerHTML = '<div class="empty">Select a budget to see period review.</div>';
  refs.simulationResult.innerHTML = '<div class="empty">Run a simulation to compare outcomes.</div>';
  state.lastSimulation = null;
}

async function selectBudget(budgetId) {
  state.selectedBudgetId = budgetId;
  refs.selectedBudgetBadge.textContent = `Budget: ${budgetId}`;
  renderStatusCards();
  setMessage("Loading budget intelligence details...");

  try {
    const [suggestions, adaptive, review] = await Promise.all([
      apiGet(`/budgets/${budgetId}/suggestions`),
      apiGet(`/budgets/${budgetId}/adaptive-adjustment`),
      apiGet(`/budgets/${budgetId}/review`),
    ]);

    renderSuggestions(suggestions);
    renderAdaptive(adaptive);
    renderReview(review);
    const selectedStatus = state.statuses.find((item) => item.budget_id === budgetId);
    if (selectedStatus) {
      renderHeroAndPace(selectedStatus);
      renderChart(selectedStatus, state.lastSimulation);
    }
    setMessage("Details loaded.");
  } catch (error) {
    setMessage(error.message);
  }
}

async function runSimulation() {
  if (!state.selectedBudgetId) {
    setMessage("Select a budget first.");
    return;
  }

  const reductionPercent = Number(refs.simReduction.value || 0);
  const absoluteCut = Number(refs.simAbsolute.value || 0);

  setMessage("Running what-if simulation...");
  try {
    const result = await apiPost(`/budgets/${state.selectedBudgetId}/simulate`, {
      reduction_percent: reductionPercent,
      absolute_cut: absoluteCut,
    });

    renderKV(refs.simulationResult, [
      ["Baseline Projected", toCurrency(result.baseline_projected_spend)],
      ["Simulated Projected", toCurrency(result.simulated_projected_spend)],
      ["Projected Savings", toCurrency(result.projected_savings)],
      ["Baseline Exceed Risk", result.baseline_predicted_to_exceed ? "Yes" : "No"],
      ["Simulated Exceed Risk", result.simulated_predicted_to_exceed ? "Yes" : "No"],
      ["Simulated Remaining", toCurrency(result.simulated_remaining_budget)],
    ]);
    state.lastSimulation = result;
    const selectedStatus = state.statuses.find(
      (item) => item.budget_id === state.selectedBudgetId
    );
    if (selectedStatus) {
      renderChart(selectedStatus, result);
    }
    setMessage("Simulation complete.");
  } catch (error) {
    setMessage(error.message);
  }
}

async function loadStatuses() {
  setMessage("Loading budget goal statuses...");
  try {
    const data = await apiGet("/budgets/goal-status");
    state.statuses = Array.isArray(data) ? data : [];
    renderStatusCards();

    if (!state.statuses.length) {
      clearDetails();
      refs.selectedBudgetBadge.textContent = "No budget selected";
      return;
    }

    if (!state.selectedBudgetId) {
      await selectBudget(state.statuses[0].budget_id);
    } else {
      const stillExists = state.statuses.some((item) => item.budget_id === state.selectedBudgetId);
      if (!stillExists) {
        await selectBudget(state.statuses[0].budget_id);
      } else {
        await selectBudget(state.selectedBudgetId);
      }
    }
  } catch (error) {
    refs.statusCards.innerHTML = "";
    refs.statusEmpty.classList.remove("hidden");
    clearDetails();
    setMessage(error.message);
  }
}

refs.refreshAllBtn.addEventListener("click", loadStatuses);
refs.runSimBtn.addEventListener("click", runSimulation);

clearDetails();
loadStatuses();
