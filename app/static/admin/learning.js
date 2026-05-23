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
    document.getElementById("refreshButton").addEventListener("click", loadLearningAnalytics);
    document.getElementById("windowSelect").addEventListener("change", loadLearningAnalytics);
    document.getElementById("sidebarToggle").addEventListener("click", () => {
        document.getElementById("sidebar").classList.toggle("open");
    });
    loadLearningAnalytics();
});

async function loadLearningAnalytics() {
    const windowDays = document.getElementById("windowSelect").value;
    const endpoint = `${window.CHazyAdminConfig.analyticsEndpoint}?window_days=${windowDays}`;
    hideError();
    try {
        const response = await fetch(endpoint, {headers: {"Accept": "application/json"}});
        if (!response.ok) {
            throw new Error(`Learning analytics returned HTTP ${response.status}`);
        }
        renderLearningAnalytics(await response.json());
    } catch (error) {
        showError(error.message || "Unable to load learning analytics.");
    }
}

function renderLearningAnalytics(data) {
    const learningMetrics = data.learning_progress?.metrics || [];
    const challengeMetrics = data.challenge_participation?.metrics || [];
    const fluencyTrend = data.trends?.fluency_score || [];

    document.getElementById("trackedIssues").textContent = metricValue(learningMetrics, "Tracked Issues");
    document.getElementById("vocabularyWords").textContent = metricValue(learningMetrics, "Vocabulary Words");
    document.getElementById("completedChallenges").textContent = metricValue(challengeMetrics, "Completed Challenges");
    document.getElementById("latestFluency").textContent = latestNonZero(fluencyTrend);

    renderMistakeCategories(data.learning_issue_categories || []);
    renderLineChart("vocabularyGrowthChart", "Vocabulary Words", data.trends?.vocabulary_words || [], chartColors.teal);
    renderLineChart("challengeParticipationChart", "Challenge Completions", data.trends?.challenge_completions || [], chartColors.amber);
    renderFluencyTrend(fluencyTrend);
    renderPracticeMix(data);
    renderLearningStatsTable([...learningMetrics, ...challengeMetrics]);
}

function renderMistakeCategories(categories) {
    const labels = categories.length ? categories.map(item => titleize(item.category)) : ["No tracked mistakes"];
    const values = categories.length ? categories.map(item => item.count) : [0];
    replaceChart("mistakeCategoryChart", {
        type: "doughnut",
        data: {
            labels,
            datasets: [{
                data: values,
                backgroundColor: [chartColors.rose, chartColors.amber, chartColors.blue, chartColors.teal, chartColors.violet],
                borderWidth: 0
            }]
        },
        options: {
            responsive: true,
            plugins: {legend: {position: "bottom"}}
        }
    });
}

function renderFluencyTrend(points) {
    replaceChart("fluencyTrendChart", {
        type: "line",
        data: {
            labels: points.map(point => point.date),
            datasets: [lineDataset("Average Fluency Score", points, chartColors.blue)]
        },
        options: {
            ...lineOptions(),
            scales: {
                x: {ticks: {maxTicksLimit: 8}, grid: {display: false}},
                y: {beginAtZero: true, max: 100, ticks: {precision: 0}}
            }
        }
    });
}

function renderPracticeMix(data) {
    const metrics = [
        ["Vocabulary Words", numberFrom(metricValue(data.learning_progress?.metrics || [], "Vocabulary Words"))],
        ["Challenges", numberFrom(metricValue(data.challenge_participation?.metrics || [], "Completed Challenges"))],
        ["Practice Messages", numberFrom(metricValue(data.engagement?.metrics || [], "Practice Messages"))],
        ["Pronunciation", numberFrom(metricValue(data.learning_progress?.metrics || [], "Pronunciation Sessions"))]
    ];
    replaceChart("practiceMixChart", {
        type: "bar",
        data: {
            labels: metrics.map(item => item[0]),
            datasets: [{
                label: "Learning Activity",
                data: metrics.map(item => item[1]),
                backgroundColor: [chartColors.teal, chartColors.amber, chartColors.blue, chartColors.violet],
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

function renderLearningStatsTable(metrics) {
    document.getElementById("learningStatsTable").innerHTML = metrics.map(metric => `
        <tr>
            <td>${escapeHtml(metric.label)}</td>
            <td class="fw-bold">${escapeHtml(metric.value)}</td>
            <td class="text-secondary">${escapeHtml(metric.detail)}</td>
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

function latestNonZero(points) {
    const point = [...points].reverse().find(item => item.value > 0);
    return point ? point.value : 0;
}

function numberFrom(value) {
    const parsed = Number(String(value || "0").replace(/[^0-9.-]/g, ""));
    return Number.isFinite(parsed) ? parsed : 0;
}

function titleize(value) {
    return String(value || "uncategorized").replaceAll("_", " ").replace(/\b\w/g, char => char.toUpperCase());
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
