import Link from "next/link";

import LegalPage, { Contact } from "@/components/layout/LegalPage";

export default function Privacy() {
  return (
    <LegalPage title="Privacy" updated="October 2026">
      <p>SuperMusic keeps as little about you as it can to work. There are no ads, no tracking cookies and no analytics services.</p>

      <h2>What we keep</h2>
      <ul>
        <li><b>Your account:</b> username, display name, bio, and your email if you gave one. Your password is stored only as a one-way hash.</li>
        <li><b>Songs you upload</b> for stems or MIDI, and the results: kept so you can download them, then deleted automatically after about a week.</li>
        <li><b>Libraries you import</b> (CSVs, Spotify or Apple Music exports): used to draw your map. The song list behind your own map is kept while you have an account. Uploaded export files are deleted after about a week.</li>
        <li><b>Maps you share:</b> stored until you delete them. A listed map is public. You choose whether play counts and listening times are included.</li>
        <li><b>Song fixes, votes, follows, pins and quiz scores</b> you make. Votes also store a one-way hash of your IP address, so one person can&apos;t vote many times.</li>
        <li><b>Server logs</b> with IP addresses, kept for a short time to fix problems and stop abuse.</li>
      </ul>

      <h2>In your browser</h2>
      <p>Your browser stores your sign-in token, a random id that lets your song fixes count as one listener&apos;s when you&apos;re signed out, and a few preferences. This is local storage, not cookies, and it never leaves your device except to talk to SuperMusic.</p>

      <h2>Other services</h2>
      <p>To fill in genres, tempo and other details, SuperMusic looks up song titles and artist names (nothing about you) on Last.fm, MusicBrainz and Deezer. If you use &quot;Save to Spotify&quot;, your browser talks to Spotify directly under your Spotify account. Links to YouTube and Spotify open those services, which have their own privacy policies.</p>

      <h2>Your choices</h2>
      <ul>
        <li>Delete any shared map from your profile.</li>
        <li>Delete your account and everything it made on the <Link href="/account" className="text-fuchsia-300 underline">account page</Link>.</li>
        <li>Ask for a copy of your data, or anything else about privacy: <Contact />.</li>
      </ul>
    </LegalPage>
  );
}
