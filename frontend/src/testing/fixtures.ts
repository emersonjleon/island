// Golden messages written by scripts/export_protocol.py (Python side of the contract).
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const dir = join(dirname(fileURLToPath(import.meta.url)), "..", "..", "..", "protocol", "fixtures");

export function fixture<T>(name: string): T {
  return JSON.parse(readFileSync(join(dir, name), "utf8")) as T;
}
