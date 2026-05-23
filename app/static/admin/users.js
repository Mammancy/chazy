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
    document.getElementById("refreshButton").addEventListener("click", loadUserAnalytics);
    document.getElementById("windowSelect").addEventListener("change", loadUserAnalytics);
    document.getElementById("sidebarToggle").addEventListener("click", () => {
        document.getElementById("sidebar").classList.toggle("open");
        document.body.classList.toggle("sidebar-collapsed");
    });
    loadUserAnalytics();
});

async function loadUserAnalytics() {
    const windowDays = document.getElementById("windowSelect").value;
    const endpoint = `${window.CHazyAdminConfig.analyticsEndpoint}?window_days=${windowDays}`;
    hideError();
    try {
        const response = await fetch(endpoint, {headers: {"Accept": "application/json"}});
        if (!response.ok) {
            throw new Error(`User analytics returned HTTP ${response.status}`);
        }
        renderUserAnalytics(await response.json());
    } catch (error) {
        showError(error.message || "Unable to load user analytics.");
    }
}

function renderUserAnalytics(data) {
    const registrations = data.trends?.new_users || [];
    const activeUsers = data.trends?.daily_active_users || [];
    const cumulativeUsers = cumulative(registrations);
    const retention = activeUsers.map((point, index) => ({
        date: point.date,
        value: percent(point.value, Math.max(cumulativeUsers[index]?.value || 0, 1))
    }));
    const averageDau = average(activeUsers.map(point => point.value));
    const latestRetention = retention.length ? retention[retention.length - 1].value : 0;

    document.getElementById("totalUsers").textContent = metricValue(data.user_growth, "Total Users");
    document.getElementById("activeLearners").textContent = metricValue(data.user_growth, "Active Learners");
    document.getElementById("avgDau").textContent = averageDau.toFixed(1);
    document.getElementById("retentionRate").textContent = `${latestRetention}%`;

    renderRegistrationChart(registrations, cumulativeUsers);
    renderActiveUsersChart(activeUsers);
    renderRetentionChart(retention);
    renderEngagementChart(data);
    renderTable("growthTable", data.user_growth?.metrics || []);
    renderTable("engagementTable", engagementMetrics(data));
}

function renderRegistrationChart(registrations, cumulativeUsers) {
    replaceChart("registrationChart", {
        type: "bar",
        data: {
            labels: registrations.map(point => point.date),
            datasets: [
                {
                    type: "bar",
                    label: "New Registrations",
                    data: registrations.map(point => point.value),
                    backgroundColor: `${chartColors.teal}99`,
                    borderRadius: 4
                },
                {
                    type: "line",
                    label: "Cumulative Users",
                    data: cumulativeUsers.map(point => point.value),
                    borderColor: chartColors.blue,
                    backgroundColor: `${chartColors.blue}22`,
                    tension: 0.35,
                    pointRadius: 2,
                    yAxisID: "y1"
                }
            ]
        },
        options: dualAxisOptions()
    });
}

function renderActiveUsersChart(points) {
    replaceChart("activeUsersChart", {
        type: "line",
        data: {
            labels: points.map(point => point.date),
            datasets: [lineDataset("Daily Active Users", points, chartColors.blue)]
        },
        options: lineOptions()
    });
}

function renderRetentionChart(points) {
    replaceChart("retentionChart", {
        type: "line",
        data: {
            labels: points.map(point => point.date),
            datasets: [lineDataset("Retention Estimate %", points, chartColors.rose)]
        },
        options: {
            ...lineOptions(),
            scales: {
                x: {ticks: {maxTicksLimit: 8}, grid: {display: false}},
                y: {beginAtZero: true, max: 100, ticks: {callback: value => `${value}%`}}
            }
        }
    });
}

function renderEngagementChart(data) {
    const metrics = engagementMetrics(data);
    replaceChart("engagementChart", {
        type: "bar",
        data: {
            labels: metrics.map(metric => metric.label),
            datasets: [{
                label: "Engagement Count",
                data: metrics.map(metric => numberFrom(metric.value)),
                backgroundColor: [chartColors.blue, chartColors.teal, chartColors.amber, chartColors.rose, chartColors.slate],
                borderRadius: 4
            }]
        },
        options: {
            responsive: true,
            plugins: {legend: {display: false}},
            scales: {
                x: {grid: {display: false}},
                y: {beginAtZero: true, ticks: {precision: 0}}
            }
        }
    });
}

function engagementMetrics(data) {
    const source = [
        ...(data.engagement?.metrics || []),
        ...(data.conversation_volume?.metrics || []),
        ...(data.challenge_participation?.metrics || [])
    ];
    return source.filter(metric => [
        "Practice Messages",
        "Vocabulary Reviews",
        "Conversations",
        "Completed Challenges",
        "Challenge Learners"
    ].includes(metric.label));
}

function renderTable(tableId, metrics) {
    document.getElementById(tableId).innerHTML = metrics.map(metric => `
        <tr>
            <td>${escapeHtml(metric.label)}</td>
            <td class="fw-bold">${escapeHtml(metric.value)}</td>
            <td class="text-secondary">${escapeHtml(metric.detail)}</td>
        </tr>
    `).join("");
}

function cumulative(points) {
    let runningTotal = 0;
    return points.map(point => {
        runningTotal += point.value;
        return {date: point.date, value: runningTotal};
    });
}

function percent(numerator, denominator) {
    return Math.min(100, Math.round((numerator / denominator) * 100));
}

function average(values) {
    if (!values.length) {
        return 0;
    }
    return values.reduce((sum, value) => sum + value, 0) / values.length;
}

function metricValue(section, label) {
    const metric = (section?.metrics || []).find(item => item.label === label);
    return metric?.value || "0";
}

function numberFrom(value) {
    const parsed = Number(String(value || "0").replace(/[^0-9.-]/g, ""));
    return Number.isFinite(parsed) ? parsed : 0;
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

function dualAxisOptions() {
    return {
        responsive: true,
        plugins: {legend: {position: "bottom"}},
        scales: {
            x: {ticks: {maxTicksLimit: 8}, grid: {display: false}},
            y: {beginAtZero: true, ticks: {precision: 0}},
            y1: {
                beginAtZero: true,
                position: "right",
                grid: {drawOnChartArea: false},
                ticks: {precision: 0}
            }
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

function escapeHtml(value) {
    return String(value ?? "")
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll("\"", "&quot;")
        .replaceAll("'", "&#039;");
}
