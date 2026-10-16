import LegalPage, { Contact } from "@/components/layout/LegalPage";

export default function Terms() {
  return (
    <LegalPage title="Terms" updated="October 2026">
      <p>By using SuperMusic you agree to these terms. SuperMusic is a free, non-commercial project.</p>

      <h2>Your music</h2>
      <ul>
        <li>Only upload music you have the right to use. Separating or transcribing a song for your own study or practice is one thing; publishing the stems or MIDI of someone else&apos;s song may need the rights holder&apos;s permission.</li>
        <li>You keep the rights to what you upload. You let SuperMusic store and process it to give you your results, and to show the maps you choose to share.</li>
      </ul>

      <h2>Fair use of the service</h2>
      <ul>
        <li>Heavy jobs wait in line, and each person has limits so everyone gets a turn. Don&apos;t try to get around them.</li>
        <li>Don&apos;t upload anything illegal, abusive or that isn&apos;t music, and don&apos;t use names, notes or map titles to harass anyone.</li>
        <li>We may remove content or close accounts that break these rules.</li>
      </ul>

      <h2>Copyright complaints</h2>
      <p>If you believe something on SuperMusic infringes your copyright, write to <Contact /> with what it is, where it is, and how to reach you. We&apos;ll take it down while we look into it.</p>

      <h2>No guarantees</h2>
      <p>SuperMusic is provided as it is. Transcriptions and maps are made by machine-learning models and can be wrong. Results are deleted after about a week, so download what you want to keep. The service may change or stop at any time.</p>

      <h2>Models and licences</h2>
      <p>Some of the models SuperMusic uses are licensed for non-commercial use only. Results made with them may carry the same limit; see the project&apos;s README for each model&apos;s licence.</p>

      <h2>Questions</h2>
      <p>Write to <Contact />.</p>
    </LegalPage>
  );
}
