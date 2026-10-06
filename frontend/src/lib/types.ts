// Types shared with the backend: generated from its OpenAPI schema (`pnpm gen:api`),
// never written by hand. A backend contract change that breaks the UI fails `tsc`.
import type { components } from "./api-schema";

type Schemas = components["schemas"];

export type CaseSummary = Schemas["CaseSummary"];
export type CasePublic = Schemas["CasePublic"];
export type OptionPublic = Schemas["OptionPublic"];
export type SubmissionIn = Schemas["SubmissionIn"];
export type SubmissionResult = Schemas["SubmissionResult"];
export type ScoredOption = Schemas["ScoredOption"];
