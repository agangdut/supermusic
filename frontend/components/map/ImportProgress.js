import { useEffect, useRef, useState } from "react";

/** "about 3 min left", "about 40 s left", "a few seconds left" */
export function formatLeft(s) {
  if (s == null) return "working out time left…";
  if (s < 5) return "a few seconds left";
  if (s < 90) return `about ${Math.round(s / 5) * 5 || 5} s left`;
  if (s < 3600) return `about ${Math.round(s / 60)} min left`;
  const h = Math.floor(s / 3600);
  return `about ${h} h ${Math.round((s - h * 3600) / 60)} min left`;
}

function formatElapsed(s) {
  s = Math.floor(s);
  return s < 60 ? `${s} s` : `${Math.floor(s / 60)} min ${String(s % 60).padStart(2, "0")} s`;
}

/** Seconds since `running` became true, ticking once a second. */
export function useElapsed(running) {
  const [elapsed, setElapsed] = useState(0);
  const start = useRef(0);
  useEffect(() => {
    if (!running) return undefined;
    start.current = Date.now();
    setElapsed(0);
    const t = setInterval(() => setElapsed((Date.now() - start.current) / 1000), 1000);
    return () => clearInterval(t);
  }, [running]);
  return elapsed;
}

const DOT = {
  done: "bg-emerald-400",
  active: "bg-fuchsia-400 animate-pulse",
  waiting: "bg-white/15",
};

/**
 * Progress of a library import. The server works out the percentage from measured
 * timings (time spent / (time spent + time left)), so the bar moves at an even pace
 * whether a song comes from the cache in milliseconds or needs a fresh lookup.
 */
export default function ImportProgress({ job, uploading, fileCount }) {
  if (uploading) {
    return (
      <Panel>
        <Row left={`Sending ${fileCount} file${fileCount > 1 ? "s" : ""} to the app…`} />
        <Bar indeterminate />
      </Panel>
    );
  }
  if (!job) return null;
  const lk = job.lookup;
  return (
    <Panel>
      <Row
        left={job.message}
        right={`${job.progress}% · ${formatLeft(job.eta_s)}`}
      />
      <Bar value={job.progress} />
      <ol className="mt-3 space-y-1.5">
        {job.steps?.map((s) => (
          <li key={s.key} className="flex items-baseline gap-2 text-xs">
            <span className={`mt-0.5 h-2 w-2 shrink-0 rounded-full ${DOT[s.state] || DOT.waiting}`} />
            <span className={s.state === "waiting" ? "text-gray-500" : "text-gray-200"}>{s.label}</span>
            {s.detail && <span className="text-gray-500">{s.detail}</span>}
          </li>
        ))}
      </ol>
      {lk && lk.todo > 0 && (
        <div className="mt-3 grid grid-cols-2 gap-2 text-[11px] sm:grid-cols-4">
          <Stat label="Found online" value={lk.found} />
          <Stat label="Not found" value={lk.not_found} />
          <Stat label="Already looked up before" value={`${lk.done_cached} of ${lk.cached}`} />
          <Stat label="Failed" value={lk.failed} warn={lk.failed > 0} />
        </div>
      )}
      {lk?.skipped > 0 && !job.warning && (
        <p className="mt-2 text-[11px] text-gray-500">
          {lk.skipped.toLocaleString()} less-played songs won&apos;t be looked up (limit {lk.todo.toLocaleString()}).
        </p>
      )}
      {job.warning && <p className="mt-2 text-[11px] text-amber-300">{job.warning}</p>}
      <div className="mt-2 flex justify-between text-[11px] text-gray-500">
        <span>{job.detected?.map((d) => `${d.file}: ${d.type}, ${d.songs.toLocaleString()} songs`).join(" · ")}</span>
        <span className="tabular-nums">{formatElapsed(job.elapsed_s || 0)} so far</span>
      </div>
    </Panel>
  );
}

/** Overlay shown while a map is (re)drawn from a CSV or the sample library. */
export function BuildProgress({ estimate }) {
  const elapsed = useElapsed(true);
  const pct = estimate ? Math.min(99, Math.round((100 * elapsed) / Math.max(estimate, 0.1))) : null;
  const left = estimate ? Math.max(estimate - elapsed, 0) : null;
  return (
    <div className="w-72 rounded-xl bg-black/40 p-4 text-xs text-gray-300 backdrop-blur">
      <Row
        left={left === 0 ? "Drawing your map… almost done" : "Drawing your map…"}
        right={estimate ? `${pct}% · ${formatLeft(left)}` : `${formatElapsed(elapsed)} so far`}
      />
      <Bar value={pct} indeterminate={pct == null} />
    </div>
  );
}

function Panel({ children }) {
  return <div className="mb-4 rounded-xl border border-white/10 bg-white/[0.03] p-4">{children}</div>;
}

function Row({ left, right }) {
  return (
    <div className="flex justify-between gap-3 text-xs text-gray-300">
      <span>{left}</span>
      {right && <span className="shrink-0 tabular-nums text-gray-500">{right}</span>}
    </div>
  );
}

function Bar({ value, indeterminate }) {
  return (
    <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-white/5">
      {indeterminate ? (
        <div className="h-1.5 w-1/3 animate-[slide_1.2s_ease-in-out_infinite] rounded-full bg-gradient-to-r from-fuchsia-500 to-indigo-500" />
      ) : (
        <div
          className="h-1.5 rounded-full bg-gradient-to-r from-fuchsia-500 to-indigo-500 transition-[width] duration-1000 ease-linear"
          style={{ width: `${value || 0}%` }}
        />
      )}
    </div>
  );
}

function Stat({ label, value, warn }) {
  return (
    <div className="rounded-lg bg-white/[0.03] px-2 py-1.5">
      <div className="text-gray-500">{label}</div>
      <div className={`tabular-nums ${warn ? "text-amber-300" : "text-gray-200"}`}>
        {typeof value === "number" ? value.toLocaleString() : value}
      </div>
    </div>
  );
}
