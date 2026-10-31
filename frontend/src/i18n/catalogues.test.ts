import { readdirSync, readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

import { SUPPORTED_LANGUAGES } from "./index";

const root = join(dirname(fileURLToPath(import.meta.url)), "..", "locales");

function keys(value: unknown, prefix = ""): string[] {
  if (value && typeof value === "object") {
    return Object.entries(value).flatMap(([k, v]) => keys(v, prefix ? `${prefix}.${k}` : k));
  }
  return [prefix];
}

describe("locale catalogues", () => {
  const namespaces = readdirSync(join(root, "en")).filter((f) => f.endsWith(".json"));
  for (const lang of SUPPORTED_LANGUAGES) {
    for (const ns of namespaces) {
      it(`${lang}/${ns} has every English key`, () => {
        const en = keys(JSON.parse(readFileSync(join(root, "en", ns), "utf8"))).sort();
        const other = keys(JSON.parse(readFileSync(join(root, lang, ns), "utf8"))).sort();
        expect(other).toEqual(en);
      });
    }
  }
});
