import Head from "next/head";
import InteractiveDemo from "@/components/Visualization/InteractiveDemo";

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
              <a
                href="#architecture"
                className="inline-flex items-center rounded-xl border border-slate-300/70 bg-white/60 px-5 py-3 font-semibold
                           text-slate-700 backdrop-blur-md transition hover:bg-white dark:border-slate-700 dark:bg-slate-900/40 dark:text-slate-200"
              >
                View demo
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
            <section
              id="architecture"
              className="mt-8 rounded-2xl border border-slate-200/70 bg-white/60 p-6 md:p-8
                        backdrop-blur-md dark:border-slate-800 dark:bg-slate-900/40"
            >
              <div className="mb-3 text-sm font-medium text-slate-700 dark:text-slate-200">
                Interactive demo (sample CSV)
              </div>
              <InteractiveDemo csvPath="D:\Code\newSuperMusic\frontend\public\data\sample_dataset.csv" height={520} />
            </section>
        </main>
      </div>
    </>
  );
}
