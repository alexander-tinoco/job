import type { Evidence } from "./types";

export interface Segment {
  text: string;
  highlighted: boolean;
  quote?: string;
}

/**
 * Split the résumé text into plain and highlighted segments.
 *
 * Works from the offsets the API returns rather than by searching for the quote
 * again: the verification already located each quote against this exact string,
 * and re-finding it in the browser would risk highlighting a different match.
 *
 * Overlapping spans are merged so a character is never emitted twice.
 */
export function segment(text: string, evidence: Evidence[]): Segment[] {
  const spans = evidence
    .filter((item): item is Evidence & { start: number; end: number } =>
      item.found && item.start !== null && item.end !== null,
    )
    .map((item) => ({ start: item.start, end: item.end, quote: item.quote }))
    .sort((a, b) => a.start - b.start);

  const segments: Segment[] = [];
  let cursor = 0;

  for (const span of spans) {
    const start = Math.max(span.start, cursor);
    if (start >= span.end) continue; // Fully inside a span already emitted.
    if (start > cursor) {
      segments.push({ text: text.slice(cursor, start), highlighted: false });
    }
    segments.push({
      text: text.slice(start, span.end),
      highlighted: true,
      quote: span.quote,
    });
    cursor = span.end;
  }

  if (cursor < text.length) {
    segments.push({ text: text.slice(cursor), highlighted: false });
  }
  return segments;
}
