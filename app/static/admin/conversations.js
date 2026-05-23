const charts = {};
const chartColors = {
    teal: "#0f766e",
    blue: "#2563eb",
    amber: "#d97706",
    rose: "#e11d48",
    slate: "#64748b",
    violet: "#7c3aed"
};

document.addEventListener("DOMContentLoaded", () => {
    const savedTheme = localStorage.getItem("chazy-admin-theme") || "light";
    setTheme(savedTheme);
    document.getElementById("themeToggle").addEventListener("click", toggleTheme);
    document.getElementById("refreshButton").addEventListener("click", loadConversationAnalytics);
    document.getElementById("windowSelect").addEventListener("change", loadConversationAnalytics);
    document.getElementById("sidebarToggle").addEventListener("click", () => {
        document.getElementById("sidebar").classList.toggle("open");
    });
    loadConversationAnalytics();
});

async function loadConversationAnalytics() {
    const windowDays = document.getElementById("windowSelect").value;
    const endpoint = `${window.CHazyAdminConfig.analyticsEndpoint}?window_days=${windowDays}`;
    hideError();
    try {
        const response = await fetch(endpoint, {headers: {"Accept": "application/json"}});
        if (!response.ok) {
            throw new Error(`Conversation analytics returned HTTP ${response.status}`);
        }
        renderConversationAnalytics(await response.json());
    } catch (error) {
        showError(error.message || "Unable to load conversation analytics.");
    }
}

function renderConversationAnalytics(data) {
    const analytics = data.conversation_analytics || {};
    const conversationMetrics = data.conversation_volume?.metrics || [];

    document.getElementById("totalConversations").textContent = metricValue(conversationMetrics, "Conversations");
    document.getElementById("savedMessages").textContent = metricValue(conversationMetrics, "Saved Messages");
    document.getElementById("avgDuration").textContent = `${analytics.average_session_duration_minutes || 0} min`;
    document.getElementById("avgMessages").textContent = analytics.average_messages_per_conversation || "0";

    renderVolumeChart(data.trends?.messages || [], data.trends?.conversations || []);
    renderLineChart("conversationFrequencyChart", "Conversation Starts", data.trends?.conversations || [], chartColors.teal);
    renderDurationChart(analytics);
    renderFeatureUsageChart(analytics.feature_usage || []);
    renderHourlyEngagementChart(analytics.engagement_by_hour || []);
    renderConversationTable(data);
}

function renderVolumeChart(messages, conversations) {
    replaceChart("messageVolumeChart", {
        type: "line",
        data: {
            labels: messages.map(point => point.date),
            datasets: [
                lineDataset("Messages", messages, chartColors.blue),
                lineDataset("Conversations", conversations, chartColors.teal)
            ]
        },
        options: lineOptions()
    });
}

function renderDurationChart(analytics) {
    replaceChart("sessionDurationChart", {
        type: "bar",
        data: {
            labels: ["Average", "Median"],
            datasets: [{
                label: "Minutes",
                data: [
                    analytics.average_session_duration_minutes || 0,
                    analytics.median_session_duration_minutes || 0
                ],
                backgroundColor: [chartColors.blue, chartColors.violet],
                borderRadius: 4
            }]
        },
        options: barOptions()
    });
}

function renderFeatureUsageChart(features) {
    const labels = features.length ? features.map(item => titleize(item.category)) : ["No feature usage"];
    const values = features.length ? features.map(item => item.count) : [0];
    replaceChart("featureUsageChart", {
        type: "doughnut",
        data: {
            labels,
            datasets: [{
                data: values,
                backgroundColor: [chartColors.blue, chartColors.teal, chartColors.amber, chartColors.rose, chartColors.violet],
                borderWidth: 0
            }]
        },
        options: {
            responsive: true,
            plugins: {legend: {position: "bottom"}}
        }
    });
}

function renderHourlyEngagementChart(points) {
    replaceChart("hourlyEngagementChart", {
        type: "bar",
        data: {
            labels: points.map(point => point.date),
            datasets: [{
                label: "Messages",
                data: points.map(point => point.value),
                backgroundColor: `${chartColors.amber}aa`,
                borderRadius: 4
            }]
        },
        options: barOptions(12)
    });
}

function renderLineChart(canvasId, label, points, color) {
    replaceChart(canvasId, {
        type: "line",
        data: {
            labels: points.map(point => point.date),
            datasets: [lineDataset(label, points, color)]
        },
        options: lineOptions()
    });
}

function renderConversationTable(data) {
    const analytics = data.conversation_analytics || {};
    const rows = [
        ["Average Session Duration", `${analytics.average_session_duration_minutes || 0} min`, "Estimated from first to last message in each conversation."],
        ["Median Session Duration", `${analytics.median_session_duration_minutes || 0} min`, "Middle duration across conversations with at least two messages."],
        ["Average Messages / Conversation", analytics.average_messages_per_conversation || 0, "Saved message depth per conversation."],
        ["Active Conversation Days", analytics.active_conversation_days || 0, "Days in the selected window with new conversations."],
        ...((data.conversation_volume?.metrics || []).map(metric => [metric.label, metric.value, metric.detail]))
    ];
    document.getElementById("conversationTable").innerHTML = rows.map(row => `
        <tr>
            <td>${escapeHtml(row[0])}</td>
            <td class="fw-bold">${escapeHtml(row[1])}</td>
            <td class="text-secondary">${escapeHtml(row[2])}</td>
        </tr>
    `).join("");
}

function lineDataset(label, points, color) {
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
        plugins: {legend: {position: "bottom"}},
        scales: {
            x: {ticks: {maxTicksLimit: 8}, grid: {display: false}},
            y: {beginAtZero: true, ticks: {precision: 0}}
        }
    };
}

function barOptions(maxTicksLimit = 8) {
    return {
        responsive: true,
        plugins: {legend: {display: false}},
        scales: {
            x: {ticks: {maxTicksLimit}, grid: {display: false}},
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

function metricValue(metrics, label) {
    const metric = metrics.find(item => item.label === label);
    return metric?.value || "0";
}

function titleize(value) {
    return String(value || "unknown").replaceAll("_", " ").replace(/\b\w/g, char => char.toUpperCase());
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

function escapeHtml(value) {
    return String(value ?? "")
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll("\"", "&quot;")
        .replaceAll("'", "&#039;");
}
