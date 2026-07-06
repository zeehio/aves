// Minimal aves web frontend: fetches the gui config, builds one uPlot chart
// per configured axis, and appends data as it streams over /ws/data.
//
// Mirrors aves/gui.py's SensorViewerGUI as closely as a browser chart
// library allows: same axes layout (row/col/rowspan/colspan), same style
// vocabulary (xlim/ylim/xlabel/ylabel/title), same "shared zoom" behaviour
// (zoom_all_together -> uPlot cursor sync).

const statusEl = document.getElementById("status");
const chartsEl = document.getElementById("charts");

function setStatus(text, isError) {
    statusEl.textContent = text;
    statusEl.classList.toggle("error", Boolean(isError));
}

function getPlotShape(axesConfig) {
    let rows = 0;
    let cols = 0;
    for (const axis of axesConfig) {
        const r = (axis.row || 0) + (axis.rowspan || 1);
        const c = (axis.col || 0) + (axis.colspan || 1);
        rows = Math.max(rows, r);
        cols = Math.max(cols, c);
    }
    return [rows, cols];
}

function buildChart(axisConfig, syncKey) {
    const container = document.createElement("div");
    container.className = "chart";
    const [row, col] = [axisConfig.row || 0, axisConfig.col || 0];
    const rowspan = axisConfig.rowspan || 1;
    const colspan = axisConfig.colspan || 1;
    container.style.gridRow = `${row + 1} / span ${rowspan}`;
    container.style.gridColumn = `${col + 1} / span ${colspan}`;
    chartsEl.appendChild(container);

    const columns = axisConfig.columns || [];
    const legend = axisConfig.columns_legend || columns;
    const series = [{}].concat(columns.map((name, i) => ({
        label: legend[i] !== undefined ? legend[i] : name,
        stroke: `hsl(${(i * 67) % 360}, 70%, 45%)`,
        width: 2,
    })));

    const opts = {
        width: container.clientWidth || 480,
        height: 300,
        title: axisConfig.title,
        scales: {
            x: { time: false },
            ...(axisConfig.ylim ? { y: { range: axisConfig.ylim } } : {}),
        },
        axes: [
            { label: axisConfig.xlabel },
            { label: axisConfig.ylabel },
        ],
        cursor: syncKey ? { sync: { key: syncKey } } : {},
        series,
    };
    if (axisConfig.xlim) {
        opts.scales.x.range = axisConfig.xlim;
    }

    const initialData = [[]].concat(columns.map(() => []));
    const plot = new uPlot(opts, initialData, container);

    window.addEventListener("resize", () => {
        plot.setSize({ width: container.clientWidth || 480, height: 300 });
    });

    return { plot, columns };
}

async function main() {
    let config;
    try {
        const response = await fetch("/api/config");
        config = await response.json();
    } catch (err) {
        setStatus("Could not load /api/config: " + err, true);
        return;
    }

    const axesConfig = config.axes || [];
    const [rows, cols] = getPlotShape(axesConfig);
    chartsEl.style.gridTemplateColumns = `repeat(${cols}, 1fr)`;
    chartsEl.style.gridTemplateRows = `repeat(${rows}, auto)`;

    if (config.window_title) {
        document.title = config.window_title;
    }

    const syncKey = config.zoom_all_together ? "aves" : null;
    const charts = axesConfig.map((axisConfig) => buildChart(axisConfig, syncKey));
    // Read-only introspection hook (browser console, tests) -- not used by
    // this module itself.
    window.__avesCharts = charts;

    const xColumn = config.x_column;
    const proto = location.protocol === "https:" ? "wss:" : "ws:";
    const ws = new WebSocket(`${proto}//${location.host}/ws/data`);

    ws.addEventListener("open", () => setStatus("connected"));
    ws.addEventListener("close", () => setStatus("disconnected", true));
    ws.addEventListener("error", () => setStatus("connection error", true));

    window.__avesRenderCount = 0;
    ws.addEventListener("message", (event) => {
        const data = JSON.parse(event.data);
        if (data.__aves_config_changed__) {
            // The config was edited and the acquisition restarted (see
            // settings.html) -- axes/columns may have changed shape, so
            // reload rather than try to patch the existing charts.
            window.location.reload();
            return;
        }
        const xValues = data[xColumn] || [];
        for (const { plot, columns } of charts) {
            const chartData = [xValues].concat(columns.map((name) => data[name] || []));
            plot.setData(chartData);
        }
        window.__avesRenderCount++;
        // Fired once all charts have drawn the new data. Not used by this
        // module itself -- an observability hook for tests (e.g. measuring
        // publish-to-render latency) or future features.
        window.dispatchEvent(new CustomEvent("aves:data-rendered", { detail: { data } }));
    });
}

main();
