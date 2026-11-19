import { describe, expect, it } from "vitest";

import { clock, dayKey, dayName, fullWhen, shortWhen } from "./dates";

// Local times, so the tests pass in any time zone.
const at = (y: number, mo: number, d: number, h = 12, mi = 0) => new Date(y, mo - 1, d, h, mi).getTime();
const NOW = at(2026, 11, 19, 17, 30);

describe("chat dates", () => {
  it("groups lines by local calendar day", () => {
    expect(dayKey(at(2026, 11, 19, 0, 1))).toBe(dayKey(at(2026, 11, 19, 23, 59)));
    expect(dayKey(at(2026, 11, 19, 0, 1))).toBeGreaterThan(dayKey(at(2026, 11, 18, 23, 59)));
  });

  it("names today and yesterday, otherwise the date, with the year only for other years", () => {
    expect(dayName(at(2026, 11, 19, 8), NOW, "es")).toEqual({ kind: "today" });
    expect(dayName(at(2026, 11, 18, 23, 59), NOW, "es")).toEqual({ kind: "yesterday" });
    const older = dayName(at(2026, 11, 12), NOW, "es");
    expect(older.kind).toBe("date");
    if (older.kind === "date") {
      expect(older.text).toMatch(/^Jueves/);
      expect(older.text).toContain("12");
      expect(older.text).not.toContain("2026");
    }
    const lastYear = dayName(at(2025, 3, 2), NOW, "en");
    expect(lastYear.kind === "date" && lastYear.text).toContain("2025");
  });

  it("shows the time for today and a short date before", () => {
    expect(clock(at(2026, 11, 19, 7, 5))).toBe("07:05");
    expect(clock(0)).toBe("");
    expect(shortWhen(at(2026, 11, 19, 9, 41), NOW, "es")).toBe("09:41");
    expect(shortWhen(at(2026, 11, 2), NOW, "es")).toContain("2");
    expect(shortWhen(at(2026, 11, 2), NOW, "es")).not.toContain(":");
    expect(fullWhen(at(2026, 11, 2, 17, 5), "en")).toContain("2026");
  });
});
