import type { ScoredOption, SubmissionResult } from "@/lib/types";

export function ResultView({ result }: { result: SubmissionResult }) {
  const diagnoses = result.options.filter((o) => o.kind === "diagnosis");
  const management = result.options.filter((o) => o.kind === "management");
  const correct = diagnoses.reduce((best, o) => (o.points > best.points ? o : best));

  return (
    <section className="card result" aria-live="polite">
      <div className="score">
        <span className="score-value">{result.score}</span>
        <span className="score-max">/ {result.max_score} points</span>
      </div>
      <p className={result.diagnosis_correct ? "verdict ok" : "verdict bad"}>
        {result.diagnosis_correct ? "Correct diagnosis" : `Correct diagnosis: ${correct.label}`}
      </p>

      <h3>Diagnosis</h3>
      <OptionList options={diagnoses} />
      <h3>Management</h3>
      <OptionList options={management} />
    </section>
  );
}

function OptionList({ options }: { options: ScoredOption[] }) {
  return (
    <ul className="scored">
      {options.map((o) => (
        <li key={o.id} className={rowClass(o)}>
          <span className="mark" aria-label={o.chosen ? "chosen" : "not chosen"}>
            {o.chosen ? "✓" : ""}
          </span>
          <span className="label">
            {o.label}
            {o.explanation && <small>{o.explanation}</small>}
            {!o.chosen && o.kind === "management" && o.points > 0 && <small>Missed</small>}
          </span>
          <span className="points">{o.points > 0 ? `+${o.points}` : o.points}</span>
        </li>
      ))}
    </ul>
  );
}

function rowClass(o: ScoredOption): string {
  if (o.points < 0) return o.chosen ? "harmful chosen" : "harmful";
  if (o.points > 0) return o.chosen ? "good chosen" : "good";
  return o.chosen ? "neutral chosen" : "neutral";
}
