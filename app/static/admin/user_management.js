let selectedUserId = null;
let currentUsers = [];

document.addEventListener("DOMContentLoaded", () => {
    const savedTheme = localStorage.getItem("chazy-admin-theme") || "light";
    setTheme(savedTheme);
    document.getElementById("themeToggle").addEventListener("click", toggleTheme);
    document.getElementById("sidebarToggle").addEventListener("click", () => {
        document.getElementById("sidebar").classList.toggle("open");
        document.body.classList.toggle("sidebar-collapsed");
    });
    document.getElementById("refreshButton").addEventListener("click", loadUsers);
    document.getElementById("searchButton").addEventListener("click", loadUsers);
    document.getElementById("searchInput").addEventListener("keydown", event => {
        if (event.key === "Enter") {
            loadUsers();
        }
    });
    document.getElementById("statusFilter").addEventListener("change", loadUsers);
    document.getElementById("activateButton").addEventListener("click", () => updateStatus(true));
    document.getElementById("deactivateButton").addEventListener("click", () => updateStatus(false));
    document.getElementById("deleteButton").addEventListener("click", deleteSelectedUser);
    loadUsers();
});

async function loadUsers() {
    hideAlerts();
    const params = new URLSearchParams({
        status: document.getElementById("statusFilter").value,
        limit: "50",
        offset: "0"
    });
    const search = document.getElementById("searchInput").value.trim();
    if (search) {
        params.set("search", search);
    }
    try {
        const response = await fetch(`${window.CHazyAdminConfig.usersEndpoint}/?${params}`, {headers: {"Accept": "application/json"}});
        if (!response.ok) {
            throw new Error(`User list returned HTTP ${response.status}`);
        }
        const data = await response.json();
        currentUsers = data.users || [];
        renderUsers(data);
    } catch (error) {
        showError(error.message || "Unable to load users.");
    }
}

function renderUsers(data) {
    document.getElementById("totalUsers").textContent = data.total || 0;
    document.getElementById("activeShown").textContent = currentUsers.filter(user => user.is_active).length;
    document.getElementById("inactiveShown").textContent = currentUsers.filter(user => !user.is_active).length;
    document.getElementById("usersTable").innerHTML = currentUsers.map(user => `
        <tr class="user-row" data-user-id="${user.id}">
            <td>
                <div class="fw-semibold">${escapeHtml(user.full_name || "Unnamed user")}</div>
                <div class="small text-secondary">${escapeHtml(user.email || "No email")}</div>
            </td>
            <td>${statusBadge(user.is_active)}</td>
            <td>${formatNumber(user.conversation_count)}</td>
            <td>${formatNumber(user.message_count)}</td>
            <td>${formatDate(user.last_activity_at)}</td>
            <td><button class="btn btn-sm btn-outline-secondary" type="button" data-inspect="${user.id}">Inspect</button></td>
        </tr>
    `).join("");
    document.querySelectorAll("[data-inspect], .user-row").forEach(element => {
        element.addEventListener("click", event => {
            const id = event.currentTarget.dataset.inspect || event.currentTarget.dataset.userId;
            if (id) {
                loadProfile(Number(id));
            }
        });
    });
}

async function loadProfile(userId) {
    hideAlerts();
    try {
        const response = await fetch(`${window.CHazyAdminConfig.usersEndpoint}/${userId}`, {headers: {"Accept": "application/json"}});
        if (!response.ok) {
            throw new Error(`Profile returned HTTP ${response.status}`);
        }
        const profile = await response.json();
        selectedUserId = userId;
        renderProfile(profile);
    } catch (error) {
        showError(error.message || "Unable to load profile.");
    }
}

function renderProfile(profile) {
    const user = profile.user;
    document.getElementById("selectedUserLabel").textContent = `#${user.id}`;
    document.getElementById("profileName").textContent = user.full_name || user.email || `User ${user.id}`;
    document.getElementById("profileStatus").outerHTML = `<span class="badge rounded-pill ${user.is_active ? "text-bg-success" : "text-bg-secondary"}" id="profileStatus">${user.is_active ? "Active" : "Inactive"}</span>`;
    document.getElementById("profileActions").classList.remove("d-none");
    document.getElementById("profileDetails").classList.remove("empty-state");
    document.getElementById("profileDetails").innerHTML = [
        ["Email", user.email || "None"],
        ["Phone", user.phone_number || "None"],
        ["Location", [user.state, user.country].filter(Boolean).join(", ") || "None"],
        ["Timezone", user.timezone],
        ["Conversations", user.conversation_count],
        ["Messages", user.message_count],
        ["Created", formatDate(user.created_at)],
        ["Last Activity", formatDate(user.last_activity_at)]
    ].map(row => `<div class="profile-row"><span>${escapeHtml(row[0])}</span><span>${escapeHtml(row[1])}</span></div>`).join("");
    document.getElementById("activityList").innerHTML = (profile.activity_history || []).map(item => `
        <article class="activity-item">
            <div class="activity-title">
                <span>${escapeHtml(item.title)}</span>
                <span class="small text-secondary">${formatDate(item.occurred_at)}</span>
            </div>
            <p class="activity-detail">${escapeHtml(item.detail)}</p>
        </article>
    `).join("") || `<div class="empty-state">No activity history found.</div>`;
}

async function updateStatus(isActive) {
    if (!selectedUserId) {
        showError("Select a user first.");
        return;
    }
    hideAlerts();
    try {
        const response = await fetch(`${window.CHazyAdminConfig.usersEndpoint}/${selectedUserId}/status`, {
            method: "PATCH",
            headers: adminJsonHeaders(),
            body: JSON.stringify({is_active: isActive})
        });
        if (!response.ok) {
            throw new Error(`Status update returned HTTP ${response.status}`);
        }
        const data = await response.json();
        showSuccess(data.message || "Status updated.");
        await loadUsers();
        await loadProfile(selectedUserId);
    } catch (error) {
        showError(error.message || "Unable to update account status.");
    }
}

async function deleteSelectedUser() {
    if (!selectedUserId) {
        showError("Select a user first.");
        return;
    }
    if (!confirm("Delete this user account? This action cannot be undone.")) {
        return;
    }
    hideAlerts();
    try {
        const response = await fetch(`${window.CHazyAdminConfig.usersEndpoint}/${selectedUserId}`, {
            method: "DELETE",
            headers: adminJsonHeaders(false)
        });
        if (!response.ok) {
            throw new Error(`Delete returned HTTP ${response.status}`);
        }
        const data = await response.json();
        selectedUserId = null;
        showSuccess(data.message || "User deleted.");
        resetProfile();
        await loadUsers();
    } catch (error) {
        showError(error.message || "Unable to delete user.");
    }
}

function resetProfile() {
    document.getElementById("selectedUserLabel").textContent = "None";
    document.getElementById("profileName").textContent = "Select a user";
    document.getElementById("profileStatus").outerHTML = `<span class="badge rounded-pill text-bg-secondary" id="profileStatus">None</span>`;
    document.getElementById("profileDetails").className = "profile-details empty-state";
    document.getElementById("profileDetails").textContent = "Choose a user from the directory to inspect profile and activity.";
    document.getElementById("profileActions").classList.add("d-none");
    document.getElementById("activityList").innerHTML = "";
}

function statusBadge(active) {
    return `<span class="badge rounded-pill ${active ? "text-bg-success" : "text-bg-secondary"}">${active ? "Active" : "Inactive"}</span>`;
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

function showSuccess(message) {
    const box = document.getElementById("successBox");
    box.textContent = message;
    box.classList.remove("d-none");
}

function hideAlerts() {
    document.getElementById("errorBox").classList.add("d-none");
    document.getElementById("successBox").classList.add("d-none");
}

function adminJsonHeaders(includeContentType = true) {
    const headers = {
        "Accept": "application/json",
        "X-CSRF-Token": window.CHazyAdminConfig.csrfToken || ""
    };
    if (includeContentType) {
        headers["Content-Type"] = "application/json";
    }
    return headers;
}

function formatNumber(value) {
    return new Intl.NumberFormat().format(value || 0);
}

function formatDate(value) {
    if (!value) {
        return "Never";
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
