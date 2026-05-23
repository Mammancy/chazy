const charts = {};
const chartColors = {
    teal: "#0f766e",
    blue: "#2563eb",
    amber: "#d97706",
    rose: "#e11d48",
    slate: "#64748b"
};

document.addEventListener("DOMContentLoaded", () => {
    const savedTheme = localStorage.getItem("chazy-admin-theme") || "light";
    setTheme(savedTheme);
    document.getElementById("themeToggle").addEventListener("click", toggleTheme);
    document.getElementById("refreshButton").addEventListener("click", loadDashboard);
    document.getElementById("windowSelect").addEventListener("change", loadDashboard);
    document.getElementById("sidebarToggle").addEventListener("click", () => {
        document.getElementById("sidebar").classList.toggle("open");
    });
    loadDashboard();
});

async function loadDashboard() {
    const windowDays = document.getElementById("windowSelect").value;
    const endpoint = `${window.CHazyAdminConfig.analyticsEndpoint}?window_days=${windowDays}`;
    hideError();
    try {
        const response = await fetch(endpoint, {headers: {"Accept": "application/json"}});
        if (!response.ok) {
            throw new Error(`Admin analytics returned HTTP ${response.status}`);
        }
        const data = await response.json();
        renderDashboard(data);
    } catch (error) {
        showError(error.message || "Unable to load admin analytics.");
    }
}

function renderDashboard(data) {
    document.getElementById("generatedAt").textContent = formatDateTime(data.generated_at);
    document.getElementById("systemStatus").textContent = data.system_health?.status || "unknown";
    document.getElementById("apiRequests").textContent = formatNumber(data.api_consumption?.estimated_requests || 0);
    document.getElementById("apiCost").textContent = `$${Number(data.api_consumption?.estimated_cost_usd || 0).toFixed(4)}`;
    document.getElementById("apiDetail").textContent = data.api_consumption?.detail || "";

    renderMetricCards(data);
    renderGrowthChart(data);
    renderLineChart("conversationChart", "Conversation Messages", data.trends?.messages || [], chartColors.blue);
    renderLineChart("challengeChart", "Challenge Completions", data.trends?.challenge_completions || [], chartColors.amber);
    renderLineChart("vocabularyChart", "Vocabulary Words", data.trends?.vocabulary_words || [], chartColors.teal);
    renderApiChart(data.api_consumption || {});
    renderLearningTable(data.learning_progress?.metrics || []);
    renderSystemTable(data);
}

function renderMetricCards(data) {
    const grid = document.getElementById("metricGrid");
    const sections = [
        data.user_growth,
        data.engagement,
        data.conversation_volume,
        data.challenge_participation
    ];
    grid.innerHTML = sections.flatMap(section => (section?.metrics || []).slice(0, 3).map(metric => `
        <article class="metric-card">
            <span class="status-label">${escapeHtml(metric.label)}</span>
            <div class="metric-value">${escapeHtml(metric.value)}</div>
            <p class="metric-detail">${escapeHtml(metric.detail)}</p>
        </article>
    `)).join("");
}

function renderGrowthChart(data) {
    const users = data.trends?.new_users || [];
    const active = data.trends?.daily_active_users || [];
    const labels = users.map(point => point.date);
    replaceChart("growthChart", {
        type: "line",
        data: {
            labels,
            datasets: [
                dataset("New Users", users, chartColors.teal),
                dataset("Daily Active Learners", active, chartColors.blue)
            ]
        },
        options: lineOptions()
    });
}

function renderLineChart(canvasId, label, points, color) {
    replaceChart(canvasId, {
        type: "line",
        data: {
            labels: points.map(point => point.date),
            datasets: [dataset(label, points, color)]
        },
        options: lineOptions()
    });
}

function renderApiChart(api) {
    replaceChart("apiChart", {
        type: "doughnut",
        data: {
            labels: ["Prompt tokens", "Completion tokens"],
            datasets: [{
                data: [
                    api.estimated_prompt_tokens || 0,
                    api.estimated_completion_tokens || 0
                ],
                backgroundColor: [chartColors.blue, chartColors.teal],
                borderWidth: 0
            }]
        },
        options: {
            responsive: true,
            plugins: {
                legend: {position: "bottom"}
            }
        }
    });
}

function renderLearningTable(metrics) {
    document.getElementById("learningTable").innerHTML = metrics.map(metric => `
        <tr>
            <td>${escapeHtml(metric.label)}</td>
            <td class="fw-bold">${escapeHtml(metric.value)}</td>
            <td class="text-secondary">${escapeHtml(metric.detail)}</td>
        </tr>
    `).join("");
}

function renderSystemTable(data) {
    const health = data.system_health || {};
    const rows = [
        ["Status", health.status || "unknown", "Application health status"],
        ["Database", health.database_status || "unknown", "Database connectivity status"],
        ["Environment", health.environment || "unknown", "Runtime environment"],
        ["Version", health.version || "unknown", "Application version"],
        ["Estimated Tokens", formatNumber(data.api_consumption?.estimated_total_tokens || 0), "Estimated API token consumption"]
    ];
    Object.entries(health.table_counts || {}).forEach(([name, value]) => {
        rows.push([titleize(name), formatNumber(value), "Database row count"]);
    });
    document.getElementById("systemTable").innerHTML = rows.map(row => `
        <tr>
            <td>${escapeHtml(row[0])}</td>
            <td class="fw-bold">${escapeHtml(row[1])}</td>
            <td class="text-secondary">${escapeHtml(row[2])}</td>
        </tr>
    `).join("");
}

function dataset(label, points, color) {
    return {
        label,
        data: points.map(point => point.value),
        borderColor: color,
        backgroundColor: `${color}22`,
        fill: true,
        tension: 0.35,
        pointRadius: 2,
        borderWidth: 2
    };
}

function lineOptions() {
    return {
        responsive: true,
        maintainAspectRatio: true,
        plugins: {
            legend: {position: "bottom"}
        },
        scales: {
            x: {ticks: {maxTicksLimit: 8}, grid: {display: false}},
            y: {beginAtZero: true, ticks: {precision: 0}}
        }
    };
}

function replaceChart(canvasId, config) {
    if (charts[canvasId]) {
        charts[canvasId].destroy();
    }
    charts[canvasId] = new Chart(document.getElementById(canvasId), config);
}

function setTheme(theme) {
    document.documentElement.setAttribute("data-bs-theme", theme);
    document.getElementById("themeToggle").textContent = theme === "dark" ? "Light" : "Dark";
    localStorage.setItem("chazy-admin-theme", theme);
}

function toggleTheme() {
    const current = document.documentElement.getAttribute("data-bs-theme") || "light";
    setTheme(current === "dark" ? "light" : "dark");
}

function showError(message) {
    const box = document.getElementById("errorBox");
    box.textContent = message;
    box.classList.remove("d-none");
}

function hideError() {
    document.getElementById("errorBox").classList.add("d-none");
}

function formatDateTime(value) {
    if (!value) {
        return "Unknown";
    }
    return new Intl.DateTimeFormat(undefined, {
        dateStyle: "medium",
        timeStyle: "short"
    }).format(new Date(value));
}

function formatNumber(value) {
    return new Intl.NumberFormat().format(value);
}

function titleize(value) {
    return value.replaceAll("_", " ").replace(/\b\w/g, char => char.toUpperCase());
}

function escapeHtml(value) {
    return String(value ?? "")
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll("\"", "&quot;")
        .replaceAll("'", "&#039;");
}
