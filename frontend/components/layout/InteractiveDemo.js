// frontend/app/components/InteractiveDemo.js
// React 18 / Next.js (App Router) compatible
// Requires: `react-plotly.js` and `plotly.js-basic-dist` (or full `plotly.js`)
//   npm i react-plotly.js plotly.js-basic-dist
//
// Props:
//   data: Array<{ id, title, artist, x, y, z, color?, size?, url?, cluster?, tempo?, key? }>
//   height: number (optional)
//   onSelect: (ids: string[], points: object[]) => void (optional)
//   onOpenTrack: (track) => void (optional)
//
// If no `data` is passed, the component renders an empty state message.

"use client";

import React, { useMemo, useRef, useState, useEffect } from "react";
import dynamic from "next/dynamic";

// Load Plotly only on the client to avoid SSR issues
const Plot = dynamic(() => import("react-plotly.js"), { ssr: false });

/** Tiny util to coerce numeric fields safely */
const num = (v, fallback = 0) => {
  const n = Number(v);
  return Number.isFinite(n) ? n : fallback;
};

export default function InteractiveDemo({
  data = [],
  height = 520,
  onSelect,
  onOpenTrack,
}) {
  const [query, setQuery] = useState("");
  const [colorMode, setColorMode] = useState("cluster"); // "cluster" | "tempo" | "key" | "none"
  const [pointSize, setPointSize] = useState(6);
  const [selectedIds, setSelectedIds] = useState([]);
  const [hovered, setHovered] = useState(null);
  const plotRef = useRef(null);

  // Filter data by simple text query across title/artist/id
  const filtered = useMemo(() => {
    if (!query?.trim()) return data;
    const q = query.toLowerCase();
    return data.filter((d) =>
      [d.title, d.artist, d.id].some((v) => String(v || "").toLowerCase().includes(q))
    );
  }, [data, query]);

  // Build Plotly colors based on mode
  const { x, y, z, text, ids, colors, sizes, customdata } = useMemo(() => {
    const xs = [];
    const ys = [];
    const zs = [];
    const txt = [];
    const idv = [];
    const cols = [];
    const sizes = [];
    const custom = [];

    // Map categorical values to consistent-ish palette
    const catPalette = [
      "#2563eb", "#16a34a", "#ef4444", "#a855f7",
      "#f59e0b", "#0ea5e9", "#f97316", "#10b981",
      "#e11d48", "#8b5cf6", "#22c55e", "#64748b",
    ];
    const catIndex = new Map();
    let catCounter = 0;

    // Numeric color scaling helper
    let minNum = +Infinity, maxNum = -Infinity;

    for (const d of filtered) {
      const cx = num(d.x), cy = num(d.y), cz = num(d.z);
      if (!Number.isFinite(cx) || !Number.isFinite(cy) || !Number.isFinite(cz)) continue;
      xs.push(cx); ys.push(cy); zs.push(cz);
      idv.push(String(d.id ?? ""));
      txt.push(`${d.title ?? "Untitled"}${d.artist ? " — " + d.artist : ""}`);
      sizes.push(num(d.size, pointSize));

      let c;
      if (colorMode === "cluster") {
        const key = String(d.cluster ?? "0");
        if (!catIndex.has(key)) catIndex.set(key, catCounter++);
        c = catPalette[catIndex.get(key) % catPalette.length];
      } else if (colorMode === "key") {
        const key = String(d.key ?? "C");
        if (!catIndex.has(key)) catIndex.set(key, catCounter++);
        c = catPalette[catIndex.get(key) % catPalette.length];
      } else if (colorMode === "tempo") {
        const t = num(d.tempo, 120);
        minNum = Math.min(minNum, t);
        maxNum = Math.max(maxNum, t);
        c = t; // numeric for colorscale
      } else {
        c = "#1f2937"; // slate-800
      }

      cols.push(c);
      custom.push([
        d.id ?? "",
        d.title ?? "",
        d.artist ?? "",
        d.url ?? "",
        d.cluster ?? "",
        d.tempo ?? "",
        d.key ?? "",
      ]);
    }

    // If numeric colors, attach colorscale via marker later
    const numeric = colorMode === "tempo";
    return {
      x: xs, y: ys, z: zs, text: txt, ids: idv,
      colors: cols, sizes,
      customdata: custom,
      colorIsNumeric: numeric,
      minNum, maxNum,
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [filtered, colorMode, pointSize]);

  const trace = useMemo(() => {
    const base = {
      type: "scatter3d",
      mode: "markers",
      x, y, z, text,
      customdata,
      hovertemplate:
        "<b>%{text}</b><br>" +
        "id=%{customdata[0]}<br>" +
        "cluster=%{customdata[4]} tempo=%{customdata[5]} key=%{customdata[6]}<extra></extra>",
      marker: {
        size: sizes,
        opacity: 0.9,
      },
      selected: { marker: { opacity: 1 } },
      unselected: { marker: { opacity: 0.22 } },
    };

    // Numeric colorscale for "tempo", otherwise color array
    if (colorMode === "tempo") {
      return {
        ...base,
        marker: {
          ...base.marker,
          color: colors,
          colorscale: "Viridis",
          colorbar: { title: "Tempo" },
          showscale: true,
        },
      };
    } else {
      return {
        ...base,
        marker: {
          ...base.marker,
          color: colors,
          showscale: false,
        },
      };
    }
  }, [x, y, z, text, customdata, colors, sizes, colorMode]);

  const layout = useMemo(
    () => ({
      autosize: true,
      height,
      margin: { l: 0, r: 0, t: 0, b: 0 },
      scene: {
        xaxis: { title: "Dim 1", zeroline: false, showspikes: false },
        yaxis: { title: "Dim 2", zeroline: false, showspikes: false },
        zaxis: { title: "Dim 3", zeroline: false, showspikes: false },
        camera: { eye: { x: 1.6, y: 1.6, z: 1.2 } },
      },
      dragmode: "lasso",
      hovermode: "closest",
      paper_bgcolor: "rgba(0,0,0,0)",
      plot_bgcolor: "rgba(0,0,0,0)",
    }),
    [height]
  );

  const config = useMemo(
    () => ({
      displayModeBar: true,
      responsive: true,
      modeBarButtonsToAdd: ["lasso2d", "select2d", "resetScale2d"],
      toImageButtonOptions: {
        format: "png",
        filename: "supermusic-embedding",
        height,
        width: 960,
        scale: 2,
      },
    }),
    [height]
  );

  // Handle selections
  const handleSelected = (ev) => {
    if (!ev || !ev.points) {
      setSelectedIds([]);
      onSelect?.([], []);
      return;
    }
    const pts = ev.points;
    const idsSel = pts.map((p) => {
      // Use the original index within the current trace
      const idx = p.pointIndex;
      return ids[idx];
    });
    setSelectedIds(idsSel);
    onSelect?.(idsSel, pts);
  };

  // Hover info
  const handleHover = (ev) => {
    if (!ev?.points?.length) return;
    const p = ev.points[0];
    const i = p.pointIndex;
    setHovered({
      id: ids[i],
      title: text[i],
      cluster: customdata[i]?.[4],
      tempo: customdata[i]?.[5],
      key: customdata[i]?.[6],
      url: customdata[i]?.[3],
    });
  };

  const handleUnhover = () => setHovered(null);

  const resetView = () => {
    try {
      plotRef.current?.el?.relayout({
        "scene.camera": { eye: { x: 1.6, y: 1.6, z: 1.2 } },
      });
    } catch (_) {
      /* no-op */
    }
  };

  return (
    <div className="w-full grid md:grid-cols-[1fr_320px] gap-4">
      <div className="w-full rounded-2xl border border-gray-200 bg-white shadow-sm p-2">
        <div className="flex items-center gap-2 p-2">
          <input
            className="flex-1 rounded-lg border px-3 py-2 text-sm"
            placeholder="Search title, artist, or id…"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
          <select
            className="rounded-lg border px-2 py-2 text-sm"
            value={colorMode}
            onChange={(e) => setColorMode(e.target.value)}
            title="Color by"
          >
            <option value="cluster">Color: cluster</option>
            <option value="tempo">Color: tempo</option>
            <option value="key">Color: key</option>
            <option value="none">Color: none</option>
          </select>
          <label className="text-sm flex items-center gap-2">
            Size
            <input
              type="range"
              min={3}
              max={14}
              step={1}
              value={pointSize}
              onChange={(e) => setPointSize(Number(e.target.value))}
            />
          </label>
          <button
            className="rounded-lg border px-3 py-2 text-sm hover:bg-gray-50"
            onClick={resetView}
            title="Reset camera"
          >
            Reset
          </button>
        </div>

        <Plot
          ref={plotRef}
          data={[trace]}
          layout={layout}
          config={config}
          onSelected={handleSelected}
          onDeselect={() => handleSelected(null)}
          onHover={handleHover}
          onUnhover={handleUnhover}
          style={{ width: "100%", height }}
          useResizeHandler
        />
      </div>

      <aside className="rounded-2xl border border-gray-200 bg-white shadow-sm p-4">
        <h3 className="text-base font-semibold mb-2">Details</h3>

        <div className="mb-4 text-sm text-gray-600">
          <div className="flex justify-between">
            <span>Points visible</span>
            <span className="font-medium">{x.length}</span>
          </div>
          <div className="flex justify-between">
            <span>Selected</span>
            <span className="font-medium">{selectedIds.length}</span>
          </div>
        </div>

        {hovered ? (
          <div className="rounded-lg border p-3 text-sm space-y-1">
            <div className="font-medium">{hovered.title}</div>
            <div className="text-gray-600">id: {hovered.id}</div>
            <div className="text-gray-600">
              cluster: {hovered.cluster ?? "—"} • tempo: {hovered.tempo ?? "—"} • key: {hovered.key ?? "—"}
            </div>
            {hovered.url ? (
              <button
                className="mt-2 rounded-md border px-3 py-1 text-sm hover:bg-gray-50"
                onClick={() => onOpenTrack?.(hovered)}
                title="Open track"
              >
                Open Track
              </button>
            ) : null}
          </div>
        ) : (
          <div className="text-sm text-gray-500">Hover a point to see details.</div>
        )}

        {selectedIds.length > 0 && (
          <div className="mt-4">
            <h4 className="text-sm font-medium mb-2">Selected IDs</h4>
            <div className="max-h-48 overflow-auto rounded-lg border p-2 text-xs space-y-1">
              {selectedIds.map((id) => (
                <div key={id} className="font-mono">{id}</div>
              ))}
            </div>
          </div>
        )}
      </aside>
    </div>
  );
}
