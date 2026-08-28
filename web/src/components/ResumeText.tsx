import { segment } from "../lib/highlight";
import type { Evidence } from "../lib/types";

/**
 * The sanitized résumé text with the model's quotes highlighted.
 *
 * Rendered as text, never as markup: this string came from a stranger's PDF.
 * The original file is downloadable, but is never displayed inline — PDF
 * viewers execute JavaScript.
 */
export function ResumeText({
  text,
  evidence,
}: {
  text: string;
  evidence: Evidence[];
}) {
  if (!text.trim()) {
    return <p className="empty">No text was extracted from this résumé.</p>;
  }
  return (
    <div className="resume">
      {segment(text, evidence).map((part, index) =>
        part.highlighted ? (
          <mark key={index} title="Quoted as evidence">
            {part.text}
          </mark>
        ) : (
          <span key={index}>{part.text}</span>
        ),
      )}
    </div>
  );
}
