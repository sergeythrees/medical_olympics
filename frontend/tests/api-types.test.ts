// @vitest-environment node
import { readFileSync } from "node:fs";
import openapiTS, { astToString } from "openapi-typescript";
import { expect, it } from "vitest";

// The frontend types are generated from the backend's exported OpenAPI schema;
// this fails if someone changed one side and forgot `pnpm gen:api`.
it("generated API types match backend/schemas/openapi.json", async () => {
  const spec = new URL("../../backend/schemas/openapi.json", import.meta.url);
  const generated = astToString(await openapiTS(readFileSync(spec, "utf8")));
  const committed = readFileSync(new URL("../src/lib/api-schema.ts", import.meta.url), "utf8");
  expect(committed).toContain(generated.trim());
});
