import Head from "next/head";

const features = [
  {
    name: "MIDI",
    desc: "Transcribe audio to MIDI with adjustable onset sensitivity.",
    icon: "🎹",
  },
  {
    name: "CSV Enrichment",
    desc: "Augment your datasets with external sources and heuristics.",
    icon: "🧩",
  },
  {
    name: "Stems",
    desc: "Split mixes into vocals, drums, bass, and more.",
    icon: "🎛️",
  },
  {
    name: "Piano Mode",
    desc: "Piano-tuned transcription that keeps note velocity and sustain pedal.",
    icon: "🎼",
  },
  {
    name: "YouTube Download",
    desc: "Grab the audio from a YouTube link to feed into stems or MIDI.",
    icon: "📥",
  },
  {
    name: "Music Map",
    desc: "See your library as a 3D map of clusters, hidden links and picks.",
    icon: "🌌",
  },
];

const mapInsights = [
  {
    label: "Taste",
    text: "Lo-Fi is 34% of your listening but only 22% of your library.",
  },
  {
    label: "Hidden link",
    text: "87 BPM neo-soul meets 174 BPM liquid DnB: same key family, half time.",
  },
  {
    label: "For you",
    text: "Low Cities sits a Camelot step from Distant Rooftops at the same tempo.",
  },
];

export default function Home() {
  return (
    <>
      <Head>
        <title>SuperMusic</title>
        <meta name="description" content="Convert audio to MIDI, enrich CSVs, separate stems." />
      </Head>

      {/* background */}
      <div className="relative min-h-screen overflow-hidden bg-gradient-to-b from-slate-50 via-white to-slate-50 dark:from-slate-950 dark:via-slate-950 dark:to-slate-950">
        {/* softly blurred accent blobs */}
        <div aria-hidden className="pointer-events-none absolute inset-0">
          <div className="absolute -top-28 -left-20 h-72 w-72 rounded-full bg-fuchsia-400/30 blur-3xl" />
          <div className="absolute -bottom-32 -right-16 h-72 w-72 rounded-full bg-blue-400/30 blur-3xl" />
        </div>

        <main className="relative mx-auto max-w-6xl px-6 py-16 lg:px-8 lg:py-24">
          {/* header */}
          <div className="mb-12 flex items-center gap-3 text-sm text-slate-600 dark:text-slate-300">
            <span className="h-2 w-2 rounded-full bg-fuchsia-500"></span>
            SuperMusic
          </div>

          {/* hero */}
          <section className="mb-14 max-w-3xl">
            <h1 className="text-4xl font-extrabold tracking-tight text-slate-900 dark:text-white sm:text-6xl">
              SuperMusic
            </h1>
            <p className="mt-4 text-lg leading-7 text-slate-600 dark:text-slate-300">
              Convert audio to MIDI, enrich CSV metadata, separate stems, and download tracks —
              all in one simple workflow.
            </p>

            <div className="mt-8 flex flex-wrap gap-3">
              <a
                href="/upload"
                className="inline-flex items-center rounded-xl bg-gradient-to-r from-fuchsia-600 to-blue-600 px-5 py-3
                           font-semibold text-white shadow-lg shadow-fuchsia-600/20 transition hover:brightness-110 focus:outline-none focus:ring-2 focus:ring-fuchsia-400"
              >
                Get started
              </a>
              <a
                href="/map"
                className="inline-flex items-center rounded-xl border border-fuchsia-400/40 bg-fuchsia-500/10 px-5 py-3 font-semibold
                           text-fuchsia-700 backdrop-blur-md transition hover:bg-fuchsia-500/20 dark:text-fuchsia-200"
              >
                Explore your Music Map
              </a>
            </div>
          </section>

          {/* features */}
          <section className="grid gap-6 sm:grid-cols-2 lg:grid-cols-3">
            {features.map((f) => (
              <div
                key={f.name}
                className="group relative rounded-2xl border border-slate-200/70 bg-white/60 p-6 backdrop-blur-md shadow-sm
                           transition hover:-translate-y-0.5 hover:shadow-lg dark:border-slate-800 dark:bg-slate-900/40"
              >
                <div className="mb-4 inline-flex h-11 w-11 items-center justify-center rounded-xl bg-gradient-to-br
                                from-fuchsia-500 to-blue-500 text-xl text-white shadow-md">
                  {f.icon}
                </div>
                <h3 className="text-lg font-semibold text-slate-900 dark:text-white">{f.name}</h3>
                <p className="mt-2 text-sm leading-6 text-slate-600 dark:text-slate-300">{f.desc}</p>
                <div className="absolute inset-x-0 bottom-0 h-0.5 scale-x-0 bg-gradient-to-r from-fuchsia-500 to-blue-500
                                transition-transform duration-300 group-hover:scale-x-100" />
              </div>
            ))}
          </section>
          {/* music map preview */}
          <section
            id="music-map"
            className="mt-8 grid overflow-hidden rounded-2xl border border-slate-200/70 bg-white/60 backdrop-blur-md
                       dark:border-slate-800 dark:bg-slate-900/40 lg:grid-cols-5"
          >
            <a href="/map" className="group relative block bg-slate-950 lg:col-span-3">
              <img
                src="/images/music-map-preview.jpg"
                alt="Music Map: clusters of tracks shown as glowing stars in 3D"
                width={790}
                height={622}
                className="h-full w-full object-cover object-left transition duration-500 group-hover:scale-[1.02]"
              />
            </a>

            <div className="flex flex-col p-6 md:p-8 lg:col-span-2">
              <div className="text-xs font-semibold uppercase tracking-wider text-fuchsia-600 dark:text-fuchsia-300">
                Music Map
              </div>
              <h2 className="mt-2 text-2xl font-bold tracking-tight text-slate-900 dark:text-white">
                See the shape of your taste
              </h2>
              <p className="mt-3 text-sm leading-6 text-slate-600 dark:text-slate-300">
                Drop in a CSV of your library and every song becomes a star. Similar tracks cluster together,
                and the map points out what you lean towards and what you&apos;ve been missing.
              </p>

              <ul className="mt-6 space-y-3">
                {mapInsights.map((i) => (
                  <li
                    key={i.label}
                    className="rounded-xl border border-slate-200/70 bg-white/70 p-3 dark:border-slate-800 dark:bg-slate-950/40"
                  >
                    <div className="text-xs font-semibold text-fuchsia-600 dark:text-fuchsia-300">{i.label}</div>
                    <div className="mt-1 text-sm text-slate-700 dark:text-slate-200">{i.text}</div>
                  </li>
                ))}
              </ul>

              <div className="mt-6 lg:mt-auto lg:pt-6">
                <a
                  href="/map"
                  className="inline-flex items-center rounded-xl bg-gradient-to-r from-fuchsia-600 to-blue-600 px-5 py-3
                             font-semibold text-white shadow-lg shadow-fuchsia-600/20 transition hover:brightness-110"
                >
                  Open your Music Map →
                </a>
              </div>
            </div>
          </section>
        </main>
      </div>
    </>
  );
}
