// Dates for the site-wide chat, whose lines can be days old: a day heading between
// lines of different days ("Today", "Yesterday", "Thursday 12 November"), the time on
// each line and the full date when hovering it. No DOM here, so it is tested on its own.

const DAY_MS = 86_400_000;

/** Local calendar day of an epoch-ms instant, as a sortable number (yyyymmdd). */
export function dayKey(at: number): number {
  const d = new Date(at);
  return d.getFullYear() * 10_000 + (d.getMonth() + 1) * 100 + d.getDate();
}

/** "17:05", in the reader's time zone. */
export function clock(at: number): string {
  if (!at) return "";
  const d = new Date(at);
  return `${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
}

export type DayName = { kind: "today" } | { kind: "yesterday" } | { kind: "date"; text: string };

/** The heading for the day of ``at``, seen at ``now``; dates in another year show the year. */
export function dayName(at: number, now: number, locale?: string): DayName {
  const day = dayKey(at);
  if (day === dayKey(now)) return { kind: "today" };
  if (day === dayKey(now - DAY_MS)) return { kind: "yesterday" };
  const sameYear = new Date(at).getFullYear() === new Date(now).getFullYear();
  const text = new Intl.DateTimeFormat(locale, sameYear
    ? { weekday: "long", day: "numeric", month: "long" }
    : { day: "numeric", month: "long", year: "numeric" }).format(new Date(at));
  return { kind: "date", text: text.charAt(0).toLocaleUpperCase(locale) + text.slice(1) };
}

/** Short "when" for a list of conversations: the time today, otherwise the date. */
export function shortWhen(at: number, now: number, locale?: string): string {
  if (!at) return "";
  if (dayKey(at) === dayKey(now)) return clock(at);
  const sameYear = new Date(at).getFullYear() === new Date(now).getFullYear();
  return new Intl.DateTimeFormat(locale, sameYear
    ? { day: "numeric", month: "short" }
    : { day: "numeric", month: "short", year: "2-digit" }).format(new Date(at));
}

/** Full date and time for a tooltip: "12 Nov 2026, 17:05". */
export function fullWhen(at: number, locale?: string): string {
  if (!at) return "";
  return new Intl.DateTimeFormat(locale, { dateStyle: "medium", timeStyle: "short" }).format(new Date(at));
}
