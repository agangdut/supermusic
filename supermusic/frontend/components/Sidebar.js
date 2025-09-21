export default function Sidebar({
  onConvertMidi,
  onEnrichCsv,
  onSeparateStems,
  tracks = [],
  onDownloadTrack,    // (track) => void
}) {
  return (
    <aside className="fixed left-0 top-0 h-full w-64 bg-white shadow-xl p-4 overflow-y-auto">
      <h2 className="text-xl font-semibold mb-4">Actions</h2>
      <div className="space-y-3 mb-6">
        <button onClick={onConvertMidi} className="w-full bg-blue-600 text-white px-4 py-2 rounded hover:bg-blue-700">Convert to MIDI</button>
        <button onClick={onEnrichCsv} className="w-full bg-green-600 text-white px-4 py-2 rounded hover:bg-green-700">Enrich CSV Metadata</button>
        <button onClick={onSeparateStems} className="w-full bg-purple-600 text-white px-4 py-2 rounded hover:bg-purple-700">Separate Stems</button>
      </div>

      <h3 className="text-lg font-semibold mb-2">Tracks</h3>
      <ul className="space-y-2">
        {tracks.length === 0 && <li className="text-sm text-gray-500">No tracks yet.</li>}
        {tracks.map((t) => (
          <li key={t.id} className="border rounded p-2">
            <div className="text-sm font-medium truncate">{t.title || t.name}</div>
            <div className="text-xs text-gray-500 truncate">{t.source}</div>
            <div className="flex gap-2 mt-2">
              {t.source === "csv" && t.url && (
                <button
                  onClick={() => onDownloadTrack(t)}
                  className="text-xs bg-indigo-600 text-white px-2 py-1 rounded hover:bg-indigo-700"
                >
                  Download
                </button>
              )}
              {/* You could add per-track MIDI/Stems later */}
            </div>
          </li>
        ))}
      </ul>
    </aside>
  );
}

