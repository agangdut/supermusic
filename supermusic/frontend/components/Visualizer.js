import dynamic from "next/dynamic";
const Plot = dynamic(() => import("react-plotly.js"), { ssr: false });

/**
 * props:
 *  - audioStats: [{ name, duration }]
 *  - csvStats:   [{ label, count }]
 */
export default function Visualizer({ audioStats = [], csvStats = [] }) {
  const hasAudio = audioStats.length > 0;
  const hasCsv = csvStats.length > 0;

  const audioTrace = {
    x: audioStats.map(a => a.name),
    y: audioStats.map(a => a.duration),
    type: "bar",
    name: "Duration (sec)"
  };

  const csvTrace = {
    labels: csvStats.map(c => c.label),
    values: csvStats.map(c => c.count),
    type: "pie",
    hole: 0.3,
    name: "CSV Overview"
  };

  return (
    <div className="w-full max-w-5xl mx-auto space-y-8">
      {hasAudio && (
        <Plot
          data={[audioTrace]}
          layout={{ title: "Track Durations (seconds)", xaxis: { automargin: true } }}
          style={{ width: "100%", height: "420px" }}
          useResizeHandler
        />
      )}
      {hasCsv && (
        <Plot
          data={[csvTrace]}
          layout={{ title: "Top Artists / Items from CSV", showlegend: true }}
          style={{ width: "100%", height: "420px" }}
          useResizeHandler
        />
      )}
      {!hasAudio && !hasCsv && (
        <p className="text-gray-500 text-center">Upload files or a YouTube Takeout CSV to see visualizations.</p>
      )}
    </div>
  );
}
