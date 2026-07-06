// Config file editor: raw TOML text in a <textarea>, not a generated
// form -- aves.utils.parse_config_text validates syntax + the 'version'
// key on save, and the real structural validation (are these axes/columns
// actually usable?) happens for free when Restart tries to build the
// acquisition from it, via the same aves.wiring code the CLI uses.

const statusEl = document.getElementById("status");
const pathEl = document.getElementById("config-path");
const textEl = document.getElementById("config-text");
const loadPathEl = document.getElementById("load-path");

function setStatus(text, isError) {
    statusEl.textContent = text;
    statusEl.classList.toggle("error", Boolean(isError));
}

// The page was served with this embedded (see aves/web/server.py), after
// proving possession of the token via ?token=... in the URL. Sent back
// explicitly on every API call below.
function authHeaders() {
    return window.__AVES_TOKEN__ ? { "Authorization": "Bearer " + window.__AVES_TOKEN__ } : {};
}

async function errorDetail(response) {
    try {
        const body = await response.json();
        return body.detail || response.statusText;
    } catch (err) {
        return response.statusText;
    }
}

async function refreshFromServer() {
    setStatus("Loading…");
    const response = await fetch("/api/settings", { headers: authHeaders() });
    if (!response.ok) {
        setStatus("Could not load settings: " + await errorDetail(response), true);
        return;
    }
    const data = await response.json();
    textEl.value = data.text;
    pathEl.textContent = data.path;
    loadPathEl.value = data.path;
    setStatus("Loaded " + data.path);
}

async function save() {
    const response = await fetch("/api/settings", {
        method: "PUT",
        headers: { "Content-Type": "application/json", ...authHeaders() },
        body: JSON.stringify({ text: textEl.value }),
    });
    if (!response.ok) {
        setStatus("Could not save: " + await errorDetail(response), true);
        return false;
    }
    return true;
}

document.getElementById("reload-btn").addEventListener("click", refreshFromServer);

document.getElementById("save-btn").addEventListener("click", async () => {
    if (await save()) {
        setStatus("Saved " + pathEl.textContent);
    }
});

document.getElementById("load-other-btn").addEventListener("click", async () => {
    const path = loadPathEl.value;
    setStatus("Loading " + path + "…");
    const response = await fetch("/api/settings/load", {
        method: "POST",
        headers: { "Content-Type": "application/json", ...authHeaders() },
        body: JSON.stringify({ path }),
    });
    if (!response.ok) {
        setStatus("Could not load " + path + ": " + await errorDetail(response), true);
        return;
    }
    const data = await response.json();
    textEl.value = data.text;
    pathEl.textContent = data.path;
    setStatus("Loaded " + data.path);
});

document.getElementById("restart-btn").addEventListener("click", async () => {
    if (!(await save())) {
        return;
    }
    setStatus("Saved. Restarting acquisition…");
    const response = await fetch("/api/settings/restart", {
        method: "POST", headers: authHeaders(),
    });
    if (!response.ok) {
        setStatus("Restart failed: " + await errorDetail(response), true);
        return;
    }
    setStatus("Restarted. Returning to the charts…");
    setTimeout(() => { window.location.href = "/"; }, 500);
});

refreshFromServer();
