import "server-only";

import createClient from "openapi-fetch";

import type { paths } from "./api-schema";

// Only server code talks to the backend: RSC for reads, a Server Action for submissions.
// The browser never needs the API URL and there is no CORS surface.
export const api = createClient<paths>({
  baseUrl: process.env.API_URL ?? "http://localhost:8000",
  cache: "no-store",
});
