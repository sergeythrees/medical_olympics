"use client";

import { useState, useTransition } from "react";

import { submitAnswers } from "@/app/cases/[id]/actions";
import type { OptionPublic, SubmissionResult } from "@/lib/types";

import { ResultView } from "./result-view";

type Props = {
  caseId: number;
  diagnosisOptions: OptionPublic[];
  managementOptions: OptionPublic[];
};

export function AnswerForm({ caseId, diagnosisOptions, managementOptions }: Props) {
  const [participant, setParticipant] = useState("");
  const [diagnosis, setDiagnosis] = useState<number | null>(null);
  const [management, setManagement] = useState<Set<number>>(new Set());
  const [result, setResult] = useState<SubmissionResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [pending, startTransition] = useTransition();

  if (result) return <ResultView result={result} />;

  const toggle = (id: number) =>
    setManagement((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });

  const onSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (diagnosis === null || !participant.trim()) return;
    setError(null);
    startTransition(async () => {
      const outcome = await submitAnswers(caseId, {
        participant: participant.trim(),
        diagnosis_option_id: diagnosis,
        management_option_ids: [...management],
      });
      if (outcome.ok) setResult(outcome.result);
      else setError(outcome.error);
    });
  };

  return (
    <form className="card answer-form" onSubmit={onSubmit} aria-busy={pending}>
      <fieldset>
        <legend>Diagnosis</legend>
        {diagnosisOptions.map((o) => (
          <label key={o.id} className="choice">
            <input
              type="radio"
              name="diagnosis"
              value={o.id}
              checked={diagnosis === o.id}
              onChange={() => setDiagnosis(o.id)}
              disabled={pending}
            />
            {o.label}
          </label>
        ))}
      </fieldset>

      <fieldset>
        <legend>Management — select everything you would do</legend>
        {managementOptions.map((o) => (
          <label key={o.id} className="choice">
            <input
              type="checkbox"
              checked={management.has(o.id)}
              onChange={() => toggle(o.id)}
              disabled={pending}
            />
            {o.label}
          </label>
        ))}
      </fieldset>

      <div className="submit-row">
        <label className="participant">
          Your name
          <input
            value={participant}
            onChange={(e) => setParticipant(e.target.value)}
            placeholder="Dr. Ivanova"
            maxLength={300}
            required
            disabled={pending}
          />
        </label>
        <button type="submit" disabled={pending || diagnosis === null || !participant.trim()}>
          {pending ? "Scoring…" : "Submit answer"}
        </button>
      </div>
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
    </form>
  );
}
