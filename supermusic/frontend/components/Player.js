// components/Player.js
import { useState, useRef } from "react";

export default function Player({ src="/sample.mp3", title="Sample Track" }) {
  const [playing, setPlaying] = useState(false);
  const audioRef = useRef(null);

  const togglePlay = () => {
    if (!audioRef.current) return;
    if (playing) { audioRef.current.pause(); setPlaying(false); }
    else {
      audioRef.current.play()
        .then(() => setPlaying(true))
        .catch(err => console.error("Playback failed", err));
    }
  };

  return (
    <div className="bg-white shadow-lg rounded p-4 w-80">
      <audio ref={audioRef} src={src} preload="auto" />
      <div className="flex justify-between items-center">
        <p className="font-medium">{title}</p>
        <button
          onClick={togglePlay}
          className="bg-blue-600 text-white px-3 py-1 rounded hover:bg-blue-700"
        >
          {playing ? "Pause" : "Play"}
        </button>
      </div>
    </div>
  );
}
