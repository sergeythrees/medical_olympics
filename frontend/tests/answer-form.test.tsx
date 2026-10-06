import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { AnswerForm } from "@/components/answer-form";
import type { SubmissionResult } from "@/lib/types";

const submitAnswers = vi.fn();
vi.mock("@/app/cases/[id]/actions", () => ({ submitAnswers: (...args: unknown[]) => submitAnswers(...args) }));

const props = {
  caseId: 7,
  diagnosisOptions: [
    { id: 1, label: "Pulmonary embolism" },
    { id: 2, label: "Pneumonia" },
  ],
  managementOptions: [
    { id: 3, label: "Therapeutic LMWH" },
    { id: 4, label: "Warfarin" },
  ],
};

const result: SubmissionResult = {
  submission_id: 1,
  case_id: 7,
  participant: "Dr. A",
  created_at: "2026-10-06T10:00:00Z",
  score: 5,
  max_score: 15,
  diagnosis_correct: false,
  options: [
    { id: 1, kind: "diagnosis", label: "Pulmonary embolism", points: 10, explanation: null, chosen: false },
    { id: 2, kind: "diagnosis", label: "Pneumonia", points: 0, explanation: null, chosen: true },
    { id: 3, kind: "management", label: "Therapeutic LMWH", points: 5, explanation: null, chosen: true },
    { id: 4, kind: "management", label: "Warfarin", points: -5, explanation: "Teratogenic", chosen: false },
  ],
};

describe("AnswerForm", () => {
  beforeEach(() => submitAnswers.mockReset());

  it("requires a name and a diagnosis before submitting", async () => {
    const user = userEvent.setup();
    render(<AnswerForm {...props} />);
    const button = screen.getByRole("button", { name: "Submit answer" });
    expect(button).toBeDisabled();

    await user.click(screen.getByLabelText("Pneumonia"));
    expect(button).toBeDisabled();
    await user.type(screen.getByLabelText("Your name"), "Dr. A");
    expect(button).toBeEnabled();
  });

  it("submits the chosen answers and shows the score breakdown", async () => {
    submitAnswers.mockResolvedValue({ ok: true, result });
    const user = userEvent.setup();
    render(<AnswerForm {...props} />);

    await user.click(screen.getByLabelText("Pneumonia"));
    await user.click(screen.getByLabelText("Therapeutic LMWH"));
    await user.click(screen.getByLabelText("Warfarin"));
    await user.click(screen.getByLabelText("Warfarin")); // un-tick
    await user.type(screen.getByLabelText("Your name"), "  Dr. A ");
    await user.click(screen.getByRole("button", { name: "Submit answer" }));

    expect(submitAnswers).toHaveBeenCalledWith(7, {
      participant: "Dr. A",
      diagnosis_option_id: 2,
      management_option_ids: [3],
    });
    expect(await screen.findByText("5")).toBeInTheDocument();
    expect(screen.getByText("/ 15 points")).toBeInTheDocument();
    expect(screen.getByText("Correct diagnosis: Pulmonary embolism")).toBeInTheDocument();
    expect(screen.getByText("Teratogenic")).toBeInTheDocument();
  });

  it("shows the server error and keeps the answers", async () => {
    submitAnswers.mockResolvedValue({ ok: false, error: "“Dr. A” has already answered this case." });
    const user = userEvent.setup();
    render(<AnswerForm {...props} />);

    await user.click(screen.getByLabelText("Pulmonary embolism"));
    await user.type(screen.getByLabelText("Your name"), "Dr. A");
    await user.click(screen.getByRole("button", { name: "Submit answer" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("already answered");
    expect(screen.getByLabelText("Pulmonary embolism")).toBeChecked();
  });
});
