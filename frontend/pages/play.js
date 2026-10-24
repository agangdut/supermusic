import { useCallback, useEffect, useState } from "react";
import Head from "next/head";
import Link from "next/link";

import PageShell from "@/components/layout/PageShell";
import { CheckCard } from "@/components/map/QuickCheck";
import { getLeaderboards, quizAnswer, quizCheck, quizFinish, quizQuestion } from "@/lib/api";
import { useAuth } from "@/lib/auth";

function Song({ s }) {
  const facts = [s.album && `Album: ${s.album}`, s.genre, s.year].filter(Boolean);
  return (
    <div className="rounded-2xl border border-white/10 bg-white/[0.04] p-4">
      {s.title && <div className="text-lg font-semibold text-white">{s.title}</div>}
      {s.artist && <div className={s.title ? "text-sm text-gray-400" : "text-lg font-semibold text-white"}>{s.artist}</div>}
      {s.songs?.length > 0 && <div className="mt-1 text-xs text-gray-500">Songs include {s.songs.join(", ")}</div>}
      {facts.length > 0 && (
        <div className="mt-2 flex flex-wrap gap-1.5 text-[11px] text-gray-400">
          {facts.map((x) => <span key={x} className="rounded-md border border-white/10 px-1.5 py-0.5">{x}</span>)}
        </div>
      )}
    </div>
  );
}

const BONUS_AFTER = [3, 7];

export default function Play() {
  const { user } = useAuth();
  const [q, setQ] = useState(null);
  const [res, setRes] = useState(null);
  const [error, setError] = useState(null);
  const [finished, setFinished] = useState(null);
  const [name, setName] = useState("");
  const [leaders, setLeaders] = useState([]);
  const [started, setStarted] = useState(false);

  const [bonus, setBonus] = useState(null); // a "help check" question between rounds, not scored

  const next = useCallback(async () => {
    setBonus(null);
    setRes(null);
    setError(null);
    try {
      setQ(await quizQuestion());
    } catch (e) {
      setError(e.message || String(e));
    }
  }, []);
  const refreshLeaders = () => getLeaderboards().then((b) => setLeaders(b.quiz)).catch(() => {});
  useEffect(() => { refreshLeaders(); }, []);

  const pick = async (choice) => {
    if (res) return;
    try {
      setRes({ ...(await quizAnswer(q.id, choice)), choice });
    } catch (e) {
      setError(e.message || String(e));
      next();
    }
  };

  const finish = async () => {
    try {
      setFinished(await quizFinish(user ? null : name));
      refreshLeaders();
    } catch (e) {
      setError(e.message || String(e));
    }
  };

  // After rounds 3 and 7, a bonus question that helps fix the atlas's song stats
  const nextOrBonus = async () => {
    if (res && BONUS_AFTER.includes(res.round) && !bonus) {
      try {
        const { question } = await quizCheck();
        if (question) { setBonus(question); return; }
      } catch {
        // No bonus this time
      }
    }
    next();
  };

  const restart = () => { setFinished(null); setQ(null); setRes(null); setStarted(true); next(); };

  return (
    <PageShell>
      <Head><title>Music quiz · SuperMusic</title></Head>
      <div className="mx-auto grid max-w-5xl gap-8 lg:grid-cols-[1fr_300px]">
        <div>
          <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-fuchsia-300">Play</div>
          <h1 className="mt-1 text-2xl font-bold tracking-tight text-white sm:text-3xl">Music quiz</h1>
          <p className="mt-1 text-sm text-gray-400">Ten questions about the music on the community atlas: when songs and albums came out, who recorded them, and what came first.</p>

          {!started && (
            <button onClick={restart} className="mt-6 rounded-xl bg-gradient-to-r from-fuchsia-600 to-indigo-600 px-6 py-3 text-sm font-semibold text-white shadow-lg shadow-fuchsia-600/20 hover:brightness-110">
              Start a round
            </button>
          )}
          {error && <p className="mt-4 text-sm text-rose-300">{error}</p>}

          {started && q && !finished && (
            <div className="mt-6 rounded-3xl border border-white/10 bg-white/[0.02] p-5 md:p-6">
              <div className="flex items-center justify-between text-xs text-gray-500">
                <span>Question {q.round} of {q.rounds}</span>
                <span>Score {res ? res.score : q.score}</span>
              </div>
              <div className="mt-1 h-1 rounded-full bg-white/5">
                <div className="h-1 rounded-full bg-gradient-to-r from-fuchsia-500 to-indigo-500" style={{ width: `${(q.round / q.rounds) * 100}%` }} />
              </div>
              <p className="mt-4 text-lg font-semibold text-white">{q.prompt}</p>
              <div className="mt-3">
                {q.song && <Song s={q.song} />}
              </div>
              <div className="mt-4 grid gap-2 sm:grid-cols-2">
                {q.options.map((o) => {
                  const right = res && o.id === res.answer;
                  const wrong = res && o.id === res.choice && !res.correct;
                  return (
                    <button key={o.id} onClick={() => pick(o.id)} disabled={!!res}
                      className={`rounded-xl border px-4 py-3 text-left text-sm transition ${
                        right ? "border-emerald-400/60 bg-emerald-400/10 text-emerald-100"
                          : wrong ? "border-rose-400/60 bg-rose-400/10 text-rose-100"
                            : "border-white/10 text-gray-200 hover:border-fuchsia-400/40 hover:bg-white/5"}`}>
                      <div className="font-medium">{o.label}</div>
                      {o.hint && <div className="truncate text-[11px] text-gray-500">{o.hint}</div>}
                    </button>
                  );
                })}
              </div>
              {res && (
                <div className="mt-4 flex flex-wrap items-center justify-between gap-3">
                  <p className={`text-sm ${res.correct ? "text-emerald-300" : "text-rose-300"}`}>
                    {res.correct ? "Right! " : "Not quite. "}<span className="text-gray-400">{res.explain}</span>
                  </p>
                  {res.done
                    ? <button onClick={() => setFinished({ pending: true, score: res.score, rounds: res.rounds })} className="rounded-xl bg-white/10 px-4 py-2 text-sm text-white hover:bg-white/15">See your score</button>
                    : !bonus && <button onClick={nextOrBonus} className="rounded-xl bg-white/10 px-4 py-2 text-sm text-white hover:bg-white/15">Next →</button>}
                </div>
              )}
              {bonus && (
                <div className="mt-4">
                  <p className="mb-2 text-xs text-gray-400">Bonus round, no score: help fix the atlas. Answer if you know it.</p>
                  <CheckCard q={bonus} tone="quiz" onNext={next} nextLabel="Back to the quiz" />
                </div>
              )}
            </div>
          )}

          {finished && (
            <div className="mt-6 rounded-3xl border border-fuchsia-400/20 bg-[radial-gradient(ellipse_at_top,_#2a1660_0%,_#0b1121_65%)] p-6 text-center">
              <div className="text-5xl font-bold text-white">{finished.score}/{finished.rounds}</div>
              <p className="mt-1 text-sm text-gray-400">{finished.score >= 8 ? "You really know your music." : finished.score >= 5 ? "Solid. You know your stuff." : "Plenty more to discover. Try again?"}</p>
              {finished.pending ? (
                <div className="mx-auto mt-4 flex max-w-xs flex-col gap-2">
                  {!user && <input value={name} onChange={(e) => setName(e.target.value)} maxLength={40} placeholder="Your name for the leaderboard"
                    className="rounded-xl border border-white/10 bg-white/5 px-3 py-2 text-sm text-white placeholder:text-gray-500" />}
                  <button onClick={finish} className="rounded-xl bg-gradient-to-r from-fuchsia-600 to-indigo-600 px-4 py-2 text-sm font-semibold text-white">Save to the leaderboard</button>
                  <button onClick={restart} className="text-xs text-gray-400 hover:text-white">Skip and play again</button>
                </div>
              ) : (
                <button onClick={restart} className="mt-4 rounded-xl bg-white/10 px-4 py-2 text-sm text-white hover:bg-white/15">Play again</button>
              )}
            </div>
          )}
        </div>

        <aside className="rounded-2xl border border-white/10 bg-white/[0.03] p-5 lg:self-start">
          <h2 className="text-sm font-semibold text-white">This week&apos;s best</h2>
          {leaders.length === 0 && <p className="mt-2 text-xs text-gray-500">Nobody yet. Be the first.</p>}
          <ol className="mt-3 space-y-2">
            {leaders.map((l, i) => (
              <li key={i} className="flex items-center gap-3 text-sm">
                <span className={`w-4 text-right text-xs ${i < 3 ? "font-bold text-amber-300" : "text-gray-500"}`}>{i + 1}</span>
                {l.username ? <Link href={`/u/${l.username}`} className="min-w-0 flex-1 truncate text-gray-200 hover:text-white">{l.name}</Link>
                  : <span className="min-w-0 flex-1 truncate text-gray-200">{l.name}</span>}
                <span className="font-semibold tabular-nums text-white">{l.best}/{l.rounds}</span>
              </li>
            ))}
          </ol>
          <Link href="/maps" className="mt-4 block text-xs text-fuchsia-300 hover:underline">All charts →</Link>
        </aside>
      </div>
    </PageShell>
  );
}
