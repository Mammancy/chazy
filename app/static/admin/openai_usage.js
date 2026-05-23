const charts = {};
const chartColors = {
    teal: "#0f766e",
    blue: "#2563eb",
    amber: "#d97706",
    rose: "#e11d48"
};

document.addEventListener("DOMContentLoaded", () => {
    const savedTheme = localStorage.getItem("chazy-admin-theme") || "light";
    setTheme(savedTheme);
    document.getElementById("themeToggle").addEventListener("click", toggleTheme);
    document.getElementById("refreshButton").addEventListener("click", loadUsage);
    document.getElementById("windowSelect").addEventListener("change", loadUsage);
    document.getElementById("sidebarToggle").addEventListener("click", () => {
        document.getElementById("sidebar").classList.toggle("open");
        document.body.classList.toggle("sidebar-collapsed");
    });
    loadUsage();
});

async function loadUsage() {
    const windowDays = document.getElementById("windowSelect").value;
    const endpoint = `${window.CHazyAdminConfig.analyticsEndpoint}?window_days=${windowDays}`;
    hideError();
    try {
        const response = await fetch(endpoint, {headers: {"Accept": "application/json"}});
        if (!response.ok) {
            throw new Error(`OpenAI usage analytics returned HTTP ${response.status}`);
        }
        renderUsage(await response.json());
    } catch (error) {
        showError(error.message || "Unable to load OpenAI usage analytics.");
    }
}

function renderUsage(data) {
    const usage = data.openai_usage || {};
    document.getElementById("totalTokens").textContent = formatNumber(usage.total_tokens || 0);
    document.getElementById("requestCount").textContent = formatNumber(usage.request_count || 0);
    document.getElementById("estimatedCost").textContent = money(usage.estimated_cost_usd || 0);
    document.getElementById("avgTokens").textContent = formatNumber(usage.average_tokens_per_request || 0);
    document.getElementById("usageDetail").textContent = usage.detail || "";

    renderLineChart("tokenTrendChart", "Estimated Tokens", usage.token_trend || [], chartColors.blue);
    renderLineChart("requestTrendChart", "Requests", usage.request_trend || [], chartColors.teal);
    renderCostChart(usage.cost_trend || []);
    renderTokenSplitChart(usage);
    renderUsageTable(usage.user_usage || []);
}

function renderTokenSplitChart(usage) {
    replaceChart("tokenSplitChart", {
        type: "doughnut",
        data: {
            labels: ["Prompt Tokens", "Completion Tokens"],
            datasets: [{
                data: [usage.prompt_tokens || 0, usage.completion_tokens || 0],
                backgroundColor: [chartColors.blue, chartColors.teal],
                borderWidth: 0
            }]
        },
        options: {responsive: true, plugins: {legend: {position: "bottom"}}}
    });
}

function renderCostChart(points) {
    const dollarPoints = points.map(point => ({date: point.date, value: (point.value || 0) / 100}));
    replaceChart("costTrendChart", {
        type: "bar",
        data: {
            labels: dollarPoints.map(point => point.date),
            datasets: [{
                label: "Estimated Cost",
                data: dollarPoints.map(point => point.value),
                backgroundColor: `${chartColors.amber}aa`,
                borderRadius: 4
            }]
        },
        options: {
            responsive: true,
            plugins: {legend: {display: false}},
            scales: {
                x: {ticks: {maxTicksLimit: 8}, grid: {display: false}},
                y: {beginAtZero: true, ticks: {callback: value => money(value)}}
            }
        }
    });
}

function renderLineChart(canvasId, label, points, color) {
    replaceChart(canvasId, {
        type: "line",
        data: {
            labels: points.map(point => point.date),
            datasets: [{
                label,
                data: points.map(point => point.value),
                borderColor: color,
                backgroundColor: `${color}22`,
                fill: true,
                tension: 0.35,
                pointRadius: 2,
                borderWidth: 2
            }]
        },
        options: {
            responsive: true,
            plugins: {legend: {position: "bottom"}},
            scales: {
                x: {ticks: {maxTicksLimit: 8}, grid: {display: false}},
                y: {beginAtZero: true, ticks: {precision: 0}}
            }
        }
    });
}

function renderUsageTable(rows) {
    document.getElementById("usageTable").innerHTML = rows.map(row => `
        <tr>
            <td>
                <div class="fw-semibold">${escapeHtml(row.display_name)}</div>
                <div class="small text-secondary">${escapeHtml(row.identity)}</div>
            </td>
            <td>${formatNumber(row.request_count || 0)}</td>
            <td class="fw-bold">${formatNumber(row.estimated_tokens || 0)}</td>
            <td>${money(row.estimated_cost_usd || 0)}</td>
            <td>${formatDate(row.last_seen_at)}</td>
        </tr>
    `).join("");
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

function formatNumber(value) {
    return new Intl.NumberFormat().format(value);
}

function money(value) {
    return `$${Number(value || 0).toFixed(4)}`;
}

function formatDate(value) {
    if (!value) {
        return "Unknown";
    }
    return new Intl.DateTimeFormat(undefined, {dateStyle: "medium", timeStyle: "short"}).format(new Date(value));
}

function escapeHtml(value) {
    return String(value ?? "")
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll("\"", "&quot;")
        .replaceAll("'", "&#039;");
}
