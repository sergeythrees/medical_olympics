"use server";

import { api } from "@/lib/api";
import type { SubmissionIn, SubmissionResult } from "@/lib/types";

export type SubmitOutcome = { ok: true; result: SubmissionResult } | { ok: false; error: string };

export async function submitAnswers(caseId: number, answers: SubmissionIn): Promise<SubmitOutcome> {
  try {
    const { data, response } = await api.POST("/cases/{case_id}/submissions", {
      params: { path: { case_id: caseId } },
      body: answers,
    });
    if (data) return { ok: true, result: data };
    if (response.status === 409) return { ok: false, error: `“${answers.participant}” has already answered this case.` };
    if (response.status === 422) return { ok: false, error: "Some answers are invalid for this case. Reload and try again." };
    return { ok: false, error: `Scoring service error (${response.status}).` };
  } catch {
    return { ok: false, error: "Scoring service is unreachable. Try again in a moment." };
  }
}
