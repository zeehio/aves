// Config file editor: a structured form built from /api/settings/structured
// (the file parsed to a plain dict), mutated in place as fields are edited.
// Saving always writes JSON (see aves/web/server.py), so Save/Save & restart
// are disabled whenever the active config isn't a .json file -- edit a
// .toml config with a text editor on your machine instead.

const statusEl = document.getElementById("status");
const pathEl = document.getElementById("config-path");
const loadPathEl = document.getElementById("load-path");
const inputFieldsEl = document.getElementById("input-fields");
const guiFieldsEl = document.getElementById("gui-fields");
const outputFieldsEl = document.getElementById("output-fields");
const saveBtn = document.getElementById("save-btn");
const restartBtn = document.getElementById("restart-btn");

// The parsed config dict backing the form, mutated in place as the user
// edits fields -- so any key the form doesn't render (an axis'
// columns_legend, say) survives untouched as long as its containing
// object isn't itself rebuilt from scratch.
let configData = null;

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

// ---- small DOM helpers ----

function el(tag, props, children) {
    const node = document.createElement(tag);
    for (const [key, value] of Object.entries(props || {})) {
        if (key === "text") {
            node.textContent = value;
        } else if (key.startsWith("on")) {
            node.addEventListener(key.slice(2), value);
        } else {
            node.setAttribute(key, value);
        }
    }
    for (const child of children || []) {
        node.appendChild(child);
    }
    return node;
}

function labeled(text, input) {
    return el("label", { class: "field" }, [document.createTextNode(text + " "), input]);
}

function numberInput(value, onChange, opts) {
    const input = el("input", Object.assign({ type: "number" }, opts || {}));
    input.value = value === undefined || value === null ? "" : value;
    input.addEventListener("change", () => onChange(input.value === "" ? null : Number(input.value)));
    return input;
}

function textInput(value, onChange) {
    const input = el("input", { type: "text" });
    input.value = value === undefined || value === null ? "" : value;
    input.addEventListener("change", () => onChange(input.value));
    return input;
}

function checkboxInput(checked, onChange) {
    const input = el("input", { type: "checkbox" });
    input.checked = Boolean(checked);
    input.addEventListener("change", () => onChange(input.checked));
    return input;
}

function removeButton(onClick) {
    return el("button", { type: "button", class: "remove-row", text: "Remove", onclick: onClick });
}

// ---- columns known across the whole file, for selects/checkboxes ----

function availableColumns() {
    const columns = ["time_computer"];
    const arduinoColumns = (configData.input && configData.input.arduino && configData.input.arduino.columns) || [];
    for (const column of arduinoColumns) {
        if (column.name) {
            columns.push(column.name);
        }
    }
    return columns;
}

function columnCheckboxes(selected, onToggle) {
    const container = el("div", { class: "column-checkboxes" });
    for (const name of availableColumns()) {
        const checkbox = checkboxInput(selected.includes(name), (checked) => onToggle(name, checked));
        container.appendChild(el("label", { class: "column-checkbox" }, [checkbox, document.createTextNode(" " + name)]));
    }
    return container;
}

// ---- [input.arduino] ----

function renderInput() {
    inputFieldsEl.innerHTML = "";
    if (!configData.input || !configData.input.arduino) {
        inputFieldsEl.appendChild(el("p", { text: "No [input.arduino] section in this file." }));
        inputFieldsEl.appendChild(el("button", {
            type: "button", text: "Add [input.arduino] section",
            onclick: () => {
                configData.input = configData.input || {};
                configData.input.arduino = { baudrate: 9600, timeout: 3, columns: [] };
                renderAll();
            },
        }));
        return;
    }
    const arduino = configData.input.arduino;
    arduino.columns = arduino.columns || [];

    inputFieldsEl.appendChild(labeled("Baud rate",
        numberInput(arduino.baudrate, (v) => { arduino.baudrate = v; }, { min: 1, step: 1 })));
    inputFieldsEl.appendChild(labeled("Timeout (s)",
        numberInput(arduino.timeout, (v) => { arduino.timeout = v; }, { min: 0, step: 1 })));

    inputFieldsEl.appendChild(el("div", { class: "list-header" }, [
        el("h3", { text: "Columns" }),
        el("button", {
            type: "button", text: "+ Add column",
            onclick: () => { arduino.columns.push({ name: "", conversion_factor: 1.0 }); renderAll(); },
        }),
    ]));

    const tbody = el("tbody");
    arduino.columns.forEach((column, index) => {
        tbody.appendChild(el("tr", {}, [
            el("td", {}, [textInput(column.name, (v) => { column.name = v; renderAll(); })]),
            el("td", {}, [numberInput(column.conversion_factor, (v) => { column.conversion_factor = v; renderAll(); }, { step: "any" })]),
            el("td", {}, [removeButton(() => { arduino.columns.splice(index, 1); renderAll(); })]),
        ]));
    });
    inputFieldsEl.appendChild(el("table", { class: "rows-table" }, [
        el("thead", {}, [el("tr", {}, [el("th", { text: "Name" }), el("th", { text: "Conversion factor" }), el("th", { text: "" })])]),
        tbody,
    ]));

    inputFieldsEl.appendChild(renderInputPreview(arduino.columns));
}

// Illustrates what the Arduino sketch needs to print, and what aves turns
// it into, without requiring an actual serial connection to look at.
const EXAMPLE_RAW_VALUE = 1000;

function renderInputPreview(columns) {
    const box = el("div", { class: "input-preview" });
    if (columns.length === 0) {
        return box;
    }
    box.appendChild(el("p", { class: "hint" }, [document.createTextNode(
        "Your Arduino sketch should print one line per sample, with these "
        + columns.length + " value(s) separated by spaces, in this exact order:")]));
    box.appendChild(el("div", {
        class: "raw-line",
        text: columns.map(() => EXAMPLE_RAW_VALUE).join(" "),
    }));

    const tbody = el("tbody");
    columns.forEach((column) => {
        const factor = column.conversion_factor ?? 1;
        const converted = Math.round(EXAMPLE_RAW_VALUE * factor * 10000) / 10000;
        tbody.appendChild(el("tr", {}, [
            el("td", { text: column.name || "(unnamed)" }),
            el("td", { text: String(EXAMPLE_RAW_VALUE) }),
            el("td", { text: "× " + factor }),
            el("td", { text: "= " + converted }),
        ]));
    });
    box.appendChild(el("table", { class: "rows-table preview-table" }, [
        el("thead", {}, [el("tr", {}, [
            el("th", { text: "Column" }), el("th", { text: "Example raw value" }),
            el("th", { text: "Conversion factor" }), el("th", { text: "Value aves records" }),
        ])]),
        tbody,
    ]));
    return box;
}

// ---- [gui] ----

function renderAxis(axis, index, axesArray) {
    const box = el("fieldset", { class: "axis-box" }, [el("legend", { text: "Axis " + (index + 1) })]);

    box.appendChild(labeled("Name", textInput(axis.name, (v) => { axis.name = v; renderAll(); })));

    const grid = el("div", { class: "axis-grid" });
    grid.appendChild(labeled("Row", numberInput(axis.row ?? 0, (v) => { axis.row = v ?? 0; renderAll(); }, { min: 0, step: 1 })));
    grid.appendChild(labeled("Col", numberInput(axis.col ?? 0, (v) => { axis.col = v ?? 0; renderAll(); }, { min: 0, step: 1 })));
    grid.appendChild(labeled("Rowspan", numberInput(axis.rowspan ?? 1, (v) => { axis.rowspan = v ?? 1; renderAll(); }, { min: 1, step: 1 })));
    grid.appendChild(labeled("Colspan", numberInput(axis.colspan ?? 1, (v) => { axis.colspan = v ?? 1; renderAll(); }, { min: 1, step: 1 })));
    box.appendChild(grid);

    box.appendChild(el("p", { text: "Columns plotted on this axis:" }));
    axis.columns = axis.columns || [];
    box.appendChild(columnCheckboxes(axis.columns, (name, checked) => {
        const pos = axis.columns.indexOf(name);
        if (checked && pos === -1) {
            axis.columns.push(name);
        } else if (!checked && pos !== -1) {
            axis.columns.splice(pos, 1);
        }
        renderAll();
    }));

    box.appendChild(labeled("X label", textInput(axis.xlabel, (v) => { if (v) { axis.xlabel = v; } else { delete axis.xlabel; } renderAll(); })));
    box.appendChild(labeled("Y label", textInput(axis.ylabel, (v) => { if (v) { axis.ylabel = v; } else { delete axis.ylabel; } renderAll(); })));
    box.appendChild(labeled("Title", textInput(axis.title, (v) => { if (v) { axis.title = v; } else { delete axis.title; } renderAll(); })));

    box.appendChild(limitField("X limits", axis, "xlim"));
    box.appendChild(limitField("Y limits", axis, "ylim"));

    box.appendChild(removeButton(() => { axesArray.splice(index, 1); renderAll(); }));
    return box;
}

function limitField(label, axis, key) {
    const hasLimit = Array.isArray(axis[key]) && axis[key].length === 2;
    const wrapper = el("span", { class: "limit-field" });
    wrapper.appendChild(checkboxInput(hasLimit, (checked) => {
        if (checked) {
            axis[key] = [0, 1];
        } else {
            delete axis[key];
        }
        renderAll();
    }));
    wrapper.appendChild(document.createTextNode(" " + label + " "));
    if (hasLimit) {
        wrapper.appendChild(numberInput(axis[key][0], (v) => { axis[key][0] = v ?? 0; }, { step: "any" }));
        wrapper.appendChild(document.createTextNode(" to "));
        wrapper.appendChild(numberInput(axis[key][1], (v) => { axis[key][1] = v ?? 0; }, { step: "any" }));
    }
    return el("label", {}, [wrapper]);
}

function renderGui() {
    guiFieldsEl.innerHTML = "";
    if (!configData.gui) {
        guiFieldsEl.appendChild(el("p", { text: "No [gui] section in this file (it runs headless)." }));
        guiFieldsEl.appendChild(el("button", {
            type: "button", text: "Add [gui] section",
            onclick: () => { configData.gui = { x_column: "", zoom_all_together: true, axes: [] }; renderAll(); },
        }));
        return;
    }
    const gui = configData.gui;
    gui.axes = gui.axes || [];

    const xColumnSelect = el("select");
    xColumnSelect.addEventListener("change", () => { gui.x_column = xColumnSelect.value; });
    for (const name of availableColumns()) {
        const option = el("option", { value: name, text: name });
        option.selected = name === gui.x_column;
        xColumnSelect.appendChild(option);
    }
    guiFieldsEl.appendChild(labeled("X column", xColumnSelect));

    guiFieldsEl.appendChild(labeled("Zoom all together",
        checkboxInput(gui.zoom_all_together, (v) => { gui.zoom_all_together = v; })));
    guiFieldsEl.appendChild(labeled("Window title",
        textInput(gui.window_title, (v) => { if (v) { gui.window_title = v; } else { delete gui.window_title; } })));
    guiFieldsEl.appendChild(labeled("Refresh time (ms)",
        numberInput(gui.refresh_time_ms, (v) => { if (v === null) { delete gui.refresh_time_ms; } else { gui.refresh_time_ms = v; } }, { min: 1, step: 1 })));

    guiFieldsEl.appendChild(el("div", { class: "list-header" }, [
        el("h3", { text: "Axes (subplots)" }),
        el("button", {
            type: "button", text: "+ Add axis",
            onclick: () => { gui.axes.push({ name: "", row: gui.axes.length, col: 0, columns: [] }); renderAll(); },
        }),
    ]));

    const axesList = el("div", { class: "axes-list" });
    gui.axes.forEach((axis, index) => axesList.appendChild(renderAxis(axis, index, gui.axes)));
    guiFieldsEl.appendChild(axesList);

    guiFieldsEl.appendChild(el("h3", { text: "Layout preview" }));
    guiFieldsEl.appendChild(el("p", { class: "hint", text: "How these axes will be laid "
        + "out and roughly what each will look like -- lines are fake, just "
        + "standing in for whichever columns are plotted on that axis." }));
    guiFieldsEl.appendChild(renderAxesPreview(gui.axes));
}

// Same series color rule as app.js' buildChart(), so a column is drawn in
// the same color here as it will be on the real chart page.
function seriesColor(index) {
    return `hsl(${(index * 67) % 360}, 70%, 45%)`;
}

// Same row/col/rowspan/colspan -> grid math as app.js' getPlotShape().
function getPlotShape(axes) {
    let rows = 0;
    let cols = 0;
    for (const axis of axes) {
        rows = Math.max(rows, (axis.row ?? 0) + (axis.rowspan ?? 1));
        cols = Math.max(cols, (axis.col ?? 0) + (axis.colspan ?? 1));
    }
    return [Math.max(rows, 1), Math.max(cols, 1)];
}

// A deterministic wavy line, just to suggest "a data series lives here" --
// not real data, so a different shape per series index is enough.
function fakeSeriesPoints(width, height, seed) {
    const steps = 24;
    const points = [];
    for (let i = 0; i <= steps; i++) {
        const x = (i / steps) * width;
        const y = height / 2
            - Math.sin(i / 3 + seed) * (height * 0.32)
            - Math.sin(i / 7 + seed * 2) * (height * 0.12);
        points.push(`${x.toFixed(1)},${y.toFixed(1)}`);
    }
    return points.join(" ");
}

function renderAxisPreviewBox(axis, index) {
    const box = el("div", { class: "axis-preview-box" });
    box.style.gridRow = `${(axis.row ?? 0) + 1} / span ${axis.rowspan ?? 1}`;
    box.style.gridColumn = `${(axis.col ?? 0) + 1} / span ${axis.colspan ?? 1}`;

    box.appendChild(el("div", {
        class: "axis-preview-title",
        text: axis.title || axis.name || ("Axis " + (index + 1)),
    }));

    const columns = axis.columns || [];
    const plotArea = el("div", { class: "axis-preview-plot" });
    if (columns.length === 0) {
        plotArea.appendChild(el("div", { class: "axis-preview-empty", text: "(no columns plotted)" }));
    } else {
        const width = 200;
        const height = 70;
        const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
        svg.setAttribute("viewBox", `0 0 ${width} ${height}`);
        svg.setAttribute("preserveAspectRatio", "none");
        svg.classList.add("axis-preview-svg");
        columns.forEach((name, i) => {
            const line = document.createElementNS("http://www.w3.org/2000/svg", "polyline");
            line.setAttribute("points", fakeSeriesPoints(width, height, i * 1.7 + 1));
            line.setAttribute("fill", "none");
            line.setAttribute("stroke", seriesColor(i));
            line.setAttribute("stroke-width", "2");
            svg.appendChild(line);
        });
        plotArea.appendChild(svg);
    }
    box.appendChild(plotArea);

    if (axis.ylabel) {
        box.appendChild(el("div", { class: "axis-preview-ylabel", text: axis.ylabel }));
    }
    if (axis.xlabel) {
        box.appendChild(el("div", { class: "axis-preview-xlabel", text: axis.xlabel }));
    }
    if (columns.length > 0) {
        box.appendChild(el("div", { class: "axis-preview-legend" },
            columns.map((name, i) => el("span", {
                class: "axis-preview-legend-item",
                style: `color: ${seriesColor(i)}`,
                text: name,
            }))));
    }
    return box;
}

function renderAxesPreview(axes) {
    const container = el("div", { class: "axes-preview" });
    if (axes.length === 0) {
        container.appendChild(el("p", { class: "hint", text: "No axes yet -- add one above." }));
        return container;
    }
    const [rows, cols] = getPlotShape(axes);
    container.style.gridTemplateColumns = `repeat(${cols}, 1fr)`;
    container.style.gridTemplateRows = `repeat(${rows}, 1fr)`;
    axes.forEach((axis, index) => container.appendChild(renderAxisPreviewBox(axis, index)));
    return container;
}

// ---- [output] ----

function renderOutput() {
    outputFieldsEl.innerHTML = "";
    if (!configData.output) {
        outputFieldsEl.appendChild(el("p", { text: "No [output] section in this file (nothing is recorded to disk)." }));
        outputFieldsEl.appendChild(el("button", {
            type: "button", text: "Add [output] section",
            onclick: () => { configData.output = { columns: [] }; renderAll(); },
        }));
        return;
    }
    configData.output.columns = configData.output.columns || [];
    outputFieldsEl.appendChild(el("p", { text: "Columns saved to the recording file:" }));
    outputFieldsEl.appendChild(columnCheckboxes(configData.output.columns, (name, checked) => {
        const columns = configData.output.columns;
        const pos = columns.indexOf(name);
        if (checked && pos === -1) {
            columns.push(name);
        } else if (!checked && pos !== -1) {
            columns.splice(pos, 1);
        }
    }));
}

function renderAll() {
    if (!configData) {
        return;
    }
    renderInput();
    renderGui();
    renderOutput();
}

// ---- loading/saving ----

function setSaveable(path) {
    const saveable = path.endsWith(".json");
    saveBtn.disabled = !saveable;
    restartBtn.disabled = !saveable;
    const reason = saveable ? "" : "Saving here only works for .json config files.";
    saveBtn.title = reason;
    restartBtn.title = reason;
}

async function refreshFromServer() {
    setStatus("Loading…");
    const response = await fetch("/api/settings/structured", { headers: authHeaders() });
    if (!response.ok) {
        setStatus("Could not load settings: " + await errorDetail(response), true);
        return false;
    }
    const data = await response.json();
    configData = data.config;
    pathEl.textContent = data.path;
    loadPathEl.value = data.path;
    renderAll();
    setSaveable(data.path);
    if (data.path.endsWith(".json")) {
        setStatus("Loaded " + data.path);
    } else {
        setStatus("Loaded " + data.path + " -- this page only saves .json "
            + "config files. Edit this one with a text editor on your "
            + "computer, or use 'Load a different file' to point at a "
            + ".json config.");
    }
    return true;
}

async function save() {
    const response = await fetch("/api/settings/structured", {
        method: "PUT",
        headers: { "Content-Type": "application/json", ...authHeaders() },
        body: JSON.stringify({ config: configData }),
    });
    if (!response.ok) {
        setStatus("Could not save: " + await errorDetail(response), true);
        return false;
    }
    return true;
}

document.getElementById("reload-btn").addEventListener("click", refreshFromServer);

saveBtn.addEventListener("click", async () => {
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
    await refreshFromServer();
});

restartBtn.addEventListener("click", async () => {
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
