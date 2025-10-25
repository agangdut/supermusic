// components/demos/InteractiveDemo.js
// Interactive 3D Plotly demo with animation, camera flythrough, CSV upload,
// color-scale picker, projection toggle, decimation, PNG export.
// Next.js-friendly (dynamic import for react-plotly.js)

import React, {
  useMemo,
  useState,
  useCallback,
  useRef,
  useEffect,
} from "react";
import dynamic from "next/dynamic";

// Avoid SSR issues in Next.js
const Plot = dynamic(() => import("react-plotly.js"), { ssr: false });

/** -------------------------------------
 * Sample datasets
 * ------------------------------------*/
function makeSpiral(n = 3500, a = 0.1, b = 0.22) {
  const x = [], y = [], z = [];
  for (let i = 0; i < n; i++) {
    const t = i / 28;
    const r = a + b * t;
    x.push(r * Math.cos(t));
    y.push(r * Math.sin(t));
    z.push(t * 0.14);
  }
  return { x, y, z, name: "Spiral" };
}

function makeLissajous(
  n = 4800,
  Ax = 1,
  Ay = 1.4,
  Az = 0.8,
  a = 3,
  b = 4,
  c = 5
) {
  const x = [], y = [], z = [];
  for (let i = 0; i < n; i++) {
    const t = (i / n) * Math.PI * 12;
    x.push(Ax * Math.sin(a * t + Math.PI / 2));
    y.push(Ay * Math.sin(b * t));
    z.push(Az * Math.sin(c * t + Math.PI / 3));
  }
  return { x, y, z, name: "Lissajous" };
}

function makeBlob(n = 6000, seed = 42) {
  let s = seed >>> 0;
  const rnd = () => {
    s ^= s << 13;
    s ^= s >>> 17;
    s ^= s << 5;
    return ((s >>> 0) % 10000) / 10000;
  };
  const gauss = () => {
    let acc = 0;
    for (let i = 0; i < 6; i++) acc += rnd();
    return (acc / 6 - 0.5) * 2;
  };
  const x = [], y = [], z = [];
  for (let i = 0; i < n; i++) {
    x.push(gauss() * 1.2);
    y.push(gauss() * 0.9);
    z.push(gauss() * 0.7);
  }
  return { x, y, z, name: "Blob" };
}

/** -------------------------------------
 * CSV parser: expects headers x,y,z (case-insensitive)
 * ------------------------------------*/
function parseCSV3D(text) {
  const lines = text.split(/\r?\n/).filter(Boolean);
  if (!lines.length) return { error: "Empty file." };

  const header = lines[0].split(/,|\t/).map((h) => h.trim().toLowerCase());
  const xi = header.indexOf("x");
  const yi = header.indexOf("y");
  const zi = header.indexOf("z");
  if (xi === -1 || yi === -1 || zi === -1) {
    return { error: "CSV must contain headers: x, y, z" };
  }
  const x = [], y = [], z = [];
  for (let i = 1; i < lines.length; i++) {
    const cols = lines[i].split(/,|\t/);
    const fx = parseFloat(cols[xi]);
    const fy = parseFloat(cols[yi]);
    const fz = parseFloat(cols[zi]);
    if ([fx, fy, fz].every(Number.isFinite)) {
      x.push(fx);
      y.push(fy);
      z.push(fz);
    }
  }
  if (!x.length) return { error: "No valid numeric rows found." };
  return { x, y, z, name: "CSV Upload" };
}

/** -------------------------------------
 * Utilities
 * ------------------------------------*/
// Uniformly subsample large arrays for performance
function decimate(data, step) {
  if (!data || step <= 1) return data;
  const pick = (arr) => arr.filter((_, i) => i % step === 0);
  return {
    x: pick(data.x),
    y: pick(data.y),
    z: pick(data.z),
    name: data.name,
  };
}

// Smooth camera path on a torus-like orbit
function cameraOnOrbit(t, radius = 2.2, height = 0.5) {
  // t in radians, smoothly increasing
  const eye = {
    x: radius * Math.cos(t),
    y: radius * Math.sin(t),
    z: height * Math.sin(t * 0.7) + 0.6,
  };
  return {
    eye,
    center: { x: 0, y: 0, z: 0 },
    up: { x: 0, y: 0, z: 1 },
  };
}

/** -------------------------------------
 * Component
 * ------------------------------------*/
export default function InteractiveDemo() {
  // Data & rendering options
  const [dataset, setDataset] = useState("Spiral");
  const [csvData, setCsvData] = useState(null);
  const [colorBy, setColorBy] = useState("z"); // none | x | y | z
  const [mode, setMode] = useState("markers"); // markers | lines | lines+markers
  const [pointSize, setPointSize] = useState(3);
  const [opacity, setOpacity] = useState(0.9);
  const [showGrid, setShowGrid] = useState(true);
  const [projection, setProjection] = useState("perspective"); // perspective | orthographic
  const [colorScale, setColorScale] = useState("Viridis"); // Plotly built-ins
  const [decimation, setDecimation] = useState(1); // 1=no decimation, 2, 3, 4...
  const [error, setError] = useState("");

  // Animation state
  const [playing, setPlaying] = useState(true);
  const [speed, setSpeed] = useState(1.0); // 0.2 - 3.0
  const tRef = useRef(0); // current angle
  const rafRef = useRef(null); // requestAnimationFrame id
  const plotRef = useRef(null); // to control camera & export

  // Build the selected dataset
  const raw3d = useMemo(() => {
    if (dataset === "CSV" && csvData) return csvData;
    switch (dataset) {
      case "Spiral":
        return makeSpiral();
      case "Lissajous":
        return makeLissajous();
      case "Blob":
        return makeBlob();
      default:
        return makeSpiral();
    }
  }, [dataset, csvData]);

  // Apply decimation (performance)
  const d3d = useMemo(
    () => decimate(raw3d, Math.max(1, Math.floor(decimation))),
    [raw3d, decimation]
  );

  const colorArray = useMemo(() => {
    if (!d3d) return null;
    if (colorBy === "none") return null;
    const { x, y, z } = d3d;
    return colorBy === "x" ? x : colorBy === "y" ? y : z;
  }, [d3d, colorBy]);

  const trace = useMemo(() => {
    return {
      type: "scatter3d",
      mode,
      x: d3d?.x ?? [],
      y: d3d?.y ?? [],
      z: d3d?.z ?? [],
      name: d3d?.name ?? "Data",
      marker: {
        size: pointSize,
        opacity,
        color: colorArray ?? undefined,
        colorscale: colorArray ? colorScale : undefined,
      },
      line: {
        width: 2,
      },
      hovertemplate:
        "<b>%{fullData.name}</b><br>" +
        "x=%{x:.3f}<br>y=%{y:.3f}<br>z=%{z:.3f}<extra></extra>",
    };
  }, [d3d, mode, pointSize, opacity, colorArray, colorScale]);

  // THEME: dark scene / axes / grid
  const baseScene = useMemo(() => {
    const axisStyle = {
      showgrid: showGrid,
      gridcolor: "rgba(148,163,184,0.2)", // subtle slate grid
      gridwidth: 1,
      zeroline: false,
      showspikes: false,
      tickcolor: "rgba(226,232,240,0.8)", // light ticks
      tickfont: { color: "rgba(226,232,240,0.8)", size: 10 },
      titlefont: { color: "rgba(226,232,240,0.9)", size: 12 },
      color: "rgba(226,232,240,0.9)", // axis line color
    };

    return {
      xaxis: { title: "x", ...axisStyle },
      yaxis: { title: "y", ...axisStyle },
      zaxis: { title: "z", ...axisStyle },

      aspectmode: "cube",
      dragmode: "turntable",

      camera: { projection: { type: projection } },

      // background for the 3D scene itself
      bgcolor: "rgba(15,23,42,1)", // #0f172a style
    };
  }, [showGrid, projection]);

  const layout = useMemo(() => {
    return {
      margin: { l: 0, r: 0, t: 36, b: 0 },

      scene: baseScene,
      showlegend: false,

      // match page theme
      paper_bgcolor: "rgba(15,23,42,0)",
      plot_bgcolor: "rgba(15,23,42,0)",

      title: {
        text: `Interactive 3D • ${d3d?.name ?? ""}`,
        x: 0.02,
        y: 0.98,
        xanchor: "left",
        yanchor: "top",
        font: {
          family:
            "ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont",
          size: 14,
          color: "rgba(226,232,240,0.9)",
          weight: 500,
        },
      },

      font: {
        color: "rgba(226,232,240,0.8)", // hover labels etc
      },

      transition: { duration: 350, easing: "cubic-in-out" },
    };
  }, [baseScene, d3d?.name]);

  // Camera animation loop (smooth orbit)
  const animate = useCallback(
    (ts) => {
      // Advance angle based on speed (scaled)
      tRef.current += 0.015 * speed;
      const cam = cameraOnOrbit(tRef.current, 2.4, 0.7);

      // Update camera without full re-render
      try {
        const gd = plotRef.current?.el; // underlying plot div
        if (gd) {
          window.Plotly.relayout(gd, {
            "scene.camera": {
              ...cam,
              projection: { type: projection },
            },
          });
        }
      } catch {
        /* no-op */
      }

      rafRef.current = requestAnimationFrame(animate);
    },
    [speed, projection]
  );

  // Start/stop the animation
  useEffect(() => {
    if (playing) {
      rafRef.current = requestAnimationFrame(animate);
    } else if (rafRef.current) {
      cancelAnimationFrame(rafRef.current);
    }
    return () => {
      if (rafRef.current) cancelAnimationFrame(rafRef.current);
    };
  }, [playing, animate]);

  // CSV upload
  const onUpload = useCallback((file) => {
    if (!file) return;
    const reader = new FileReader();
    reader.onload = (e) => {
      try {
        const parsed = parseCSV3D(String(e.target?.result || ""));
        if (parsed?.error) {
          setError(parsed.error);
          setCsvData(null);
        } else {
          setError("");
          setCsvData(parsed);
          setDataset("CSV");
        }
      } catch {
        setError("Failed to parse CSV.");
        setCsvData(null);
      }
    };
    reader.readAsText(file);
  }, []);

  // Export PNG
  const onExport = useCallback(async () => {
    const gd = plotRef.current?.el;
    if (!gd) return;
    try {
      const url = await window.Plotly.toImage(gd, {
        format: "png",
        width: 1600,
        height: 900,
        scale: 2,
      });
      // trigger download
      const a = document.createElement("a");
      a.href = url;
      a.download = `supermusic-3d-${(d3d?.name || "plot").toLowerCase()}.png`;
      a.click();
      a.remove();
    } catch (e) {
      // eslint-disable-next-line no-console
      console.error("Export failed:", e);
    }
  }, [d3d?.name]);

  // Keep camera steady on first draw (prevents jump)
  const handleInitialized = useCallback((figure, graphDiv) => {
    plotRef.current = { el: graphDiv };
    // Set an initial cinematic angle
    const cam = cameraOnOrbit(tRef.current, 2.4, 0.7);
    window.Plotly.relayout(graphDiv, { "scene.camera": cam });
  }, []);

  return (
    <div className="w-full rounded-xl border border-white/10 bg-[#0f172a] p-4 text-gray-200">
      {/* Controls */}
      <div className="flex flex-wrap items-center gap-3 mb-4 text-gray-200 text-sm">
        {/* Dataset */}
        <div className="flex items-center gap-2">
          <label className="font-medium text-gray-300">Dataset:</label>
          <select
            value={dataset}
            onChange={(e) => setDataset(e.target.value)}
            className="bg-[#1e253d] text-gray-100 border border-white/10 rounded px-2 py-1 text-sm focus:outline-none focus:ring-2 focus:ring-purple-500/40"
          >
            <option>Spiral</option>
            <option>Lissajous</option>
            <option>Blob</option>
            <option>CSV</option>
          </select>
        </div>

        {/* Mode */}
        <div className="flex items-center gap-2">
          <label className="font-medium text-gray-300">Mode:</label>
          <select
            value={mode}
            onChange={(e) => setMode(e.target.value)}
            className="bg-[#1e253d] text-gray-100 border border-white/10 rounded px-2 py-1 text-sm focus:outline-none focus:ring-2 focus:ring-purple-500/40"
          >
            <option value="markers">markers</option>
            <option value="lines">lines</option>
            <option value="lines+markers">lines+markers</option>
          </select>
        </div>

        {/* Point size */}
        <div className="flex items-center gap-2">
          <label className="font-medium text-gray-300">Point size:</label>
          <input
            type="range"
            min={1}
            max={10}
            value={pointSize}
            onChange={(e) => setPointSize(Number(e.target.value))}
            className="accent-purple-500"
          />
          <span className="tabular-nums text-gray-400">{pointSize}</span>
        </div>

        {/* Opacity */}
        <div className="flex items-center gap-2">
          <label className="font-medium text-gray-300">Opacity:</label>
          <input
            type="range"
            min={0.1}
            max={1}
            step={0.05}
            value={opacity}
            onChange={(e) => setOpacity(Number(e.target.value))}
            className="accent-purple-500"
          />
          <span className="tabular-nums text-gray-400">
            {opacity.toFixed(2)}
          </span>
        </div>

        {/* Color by */}
        <div className="flex items-center gap-2">
          <label className="font-medium text-gray-300">Color by:</label>
          <select
            value={colorBy}
            onChange={(e) => setColorBy(e.target.value)}
            className="bg-[#1e253d] text-gray-100 border border-white/10 rounded px-2 py-1 text-sm focus:outline-none focus:ring-2 focus:ring-purple-500/40"
          >
            <option value="none">none</option>
            <option value="x">x</option>
            <option value="y">y</option>
            <option value="z">z</option>
          </select>
        </div>

        {/* Colorscale */}
        <div className="flex items-center gap-2">
          <label className="font-medium text-gray-300">Colorscale:</label>
          <select
            value={colorScale}
            onChange={(e) => setColorScale(e.target.value)}
            className="bg-[#1e253d] text-gray-100 border border-white/10 rounded px-2 py-1 text-sm focus:outline-none focus:ring-2 focus:ring-purple-500/40"
          >
            <option>Viridis</option>
            <option>Plasma</option>
            <option>Magma</option>
            <option>Cividis</option>
            <option>Portland</option>
            <option>Picnic</option>
            <option>Turbo</option>
            <option>Jet</option>
          </select>
        </div>

        {/* Projection */}
        <div className="flex items-center gap-2">
          <label className="font-medium text-gray-300">Projection:</label>
          <select
            value={projection}
            onChange={(e) => setProjection(e.target.value)}
            className="bg-[#1e253d] text-gray-100 border border-white/10 rounded px-2 py-1 text-sm focus:outline-none focus:ring-2 focus:ring-purple-500/40"
          >
            <option value="perspective">perspective</option>
            <option value="orthographic">orthographic</option>
          </select>
        </div>

        {/* Grid toggle */}
        <label className="inline-flex items-center gap-2 cursor-pointer text-gray-300">
          <input
            type="checkbox"
            checked={showGrid}
            onChange={(e) => setShowGrid(e.target.checked)}
            className="accent-purple-500"
          />
          <span>Grid</span>
        </label>

        {/* Decimate */}
        <div className="flex items-center gap-2">
          <label className="font-medium text-gray-300">Decimate:</label>
          <input
            type="range"
            min={1}
            max={8}
            value={decimation}
            onChange={(e) => setDecimation(Number(e.target.value))}
            className="accent-purple-500"
          />
          <span className="tabular-nums text-gray-400">×{decimation}</span>
        </div>

        {/* Play / speed */}
        <div className="flex items-center gap-2">
          <button
            onClick={() => setPlaying((p) => !p)}
            className="px-3 py-1 rounded-md border border-white/10 bg-[#1e253d] text-gray-100 text-sm hover:border-purple-500/40 hover:text-white transition-colors"
          >
            {playing ? "Pause" : "Play"}
          </button>
          <label className="font-medium text-gray-300">Speed:</label>
          <input
            type="range"
            min={0.2}
            max={3}
            step={0.1}
            value={speed}
            onChange={(e) => setSpeed(Number(e.target.value))}
            className="accent-purple-500"
          />
          <span className="tabular-nums text-gray-400">
            {speed.toFixed(1)}x
          </span>
        </div>

        {/* CSV upload */}
        <div className="flex items-center gap-2">
          <label className="font-medium text-gray-300">Upload CSV:</label>
          <input
            type="file"
            accept=".csv,text/csv"
            onChange={(e) => onUpload(e.target.files?.[0])}
            className="text-gray-300 text-xs file:mr-2 file:rounded-md file:border file:border-white/10 file:bg-[#1e253d] file:px-2 file:py-1 file:text-gray-100 hover:file:border-purple-500/40 hover:file:text-white file:text-xs file:transition-colors"
          />
        </div>

        {/* Export */}
        <button
          onClick={onExport}
          className="px-3 py-1 rounded-md border border-white/10 bg-[#1e253d] text-gray-100 text-sm hover:border-purple-500/40 hover:text-white transition-colors"
        >
          Export PNG
        </button>
      </div>

      {/* Plot */}
      <div className="w-full" style={{ height: 560 }}>
        <Plot
          data={[trace]}
          layout={{ ...layout, height: 560 }}
          config={{
            displaylogo: false,
            responsive: true,
            modeBarButtonsToRemove: ["toImage"], // we provide our own exporter
          }}
          style={{ width: "100%", height: "100%" }}
          useResizeHandler
          onInitialized={handleInitialized}
          onUpdate={(fig, gd) => {
            // keep ref fresh after interactions
            plotRef.current = { el: gd };
          }}
        />
      </div>

      <div className="mt-3 text-xs text-gray-500">
        Tip: drag to rotate • scroll to zoom • right-drag to pan • hold Shift
        for box/lasso select.
      </div>

      {dataset === "CSV" && !csvData && (
        <p className="text-xs text-gray-400 mt-3">
          CSV should include headers <code>x,y,z</code>. Extra columns are
          ignored.
        </p>
      )}
      {error && (
        <p className="text-xs text-red-500 mt-2">
          {error}
        </p>
      )}
    </div>
  );
}
