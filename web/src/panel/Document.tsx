import { useState } from "react";
import { PageIcon, TranscriptIcon } from "../components/icons";
import { api } from "../lib/api";
import { segment } from "../lib/highlight";
import type { Evidence } from "../lib/types";

/**
 * Two registers of the same page: the transcript the model actually read, and
 * the document as a human sees it.
 *
 * The pages are **images rendered server-side**, not an embedded PDF. The file
 * came from a stranger and PDF viewers execute scripts; a PNG executes nothing.
 */
export function DocumentPlate({
  applicationId,
  text,
  evidence,
  pageCount,
  activeQuote,
}: {
  applicationId: string;
  text: string;
  evidence: Evidence[];
  pageCount: number;
  activeQuote: string | null;
}) {
  const [register, setRegister] = useState<"transcript" | "pages">("transcript");

  return (
    <>
      <div className="registers">
        <button
          className="control"
          aria-pressed={register === "transcript"}
          onClick={() => setRegister("transcript")}
        >
          <TranscriptIcon /> Transcript
        </button>
        <button
          className="control"
          aria-pressed={register === "pages"}
          onClick={() => setRegister("pages")}
        >
          <PageIcon /> Document
        </button>
        <a
          className="control quiet"
          href={api.resumeUrl(applicationId)}
          style={{ marginLeft: "auto" }}
        >
          Download original
        </a>
      </div>

      {register === "transcript" ? (
        text.trim() ? (
          <div className="transcript">
            {segment(text, evidence).map((part, index) =>
              part.highlighted ? (
                <mark key={index} data-active={part.quote === activeQuote}>
                  {part.text}
                </mark>
              ) : (
                <span key={index}>{part.text}</span>
              ),
            )}
          </div>
        ) : (
          <p className="empty">
            <strong>No text was recovered</strong>
            This file has no text layer, so nothing could be read from it.
          </p>
        )
      ) : (
        <div className="pages">
          {Array.from({ length: Math.max(pageCount, 1) }, (_, index) => (
            <img
              key={index}
              src={`/api/v1/applications/${applicationId}/resume/pages/${index + 1}`}
              alt={`Page ${index + 1} of the résumé`}
              loading={index === 0 ? "eager" : "lazy"}
            />
          ))}
        </div>
      )}
    </>
  );
}
