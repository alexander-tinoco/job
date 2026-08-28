import { useEffect, useState } from "react";
import { segment } from "../lib/highlight";
import type { CriterionScore, Evidence } from "../lib/types";

/**
 * What a hiring manager sees without an account.
 *
 * Read-only by construction: there is no control on this page that writes
 * anything. Contact details and declined candidates never reach it — the person
 * reading needs the assessment, not the applicant's phone number, and who was
 * turned down is nobody else's business.
 */

interface SharedCandidate {
  id: string;
  name: string;
  overall_score: string;
  summary: string;
  relevant_years_experience: string;
  mandatory_requirements_met: boolean;
  detected_skills: string[];
  criteria: CriterionScore[];
  resume_text: string;
  page_count: number;
  tampered: boolean;
  shortlisted: boolean;
}

interface SharedView {
  opening_title: string;
  company_name: string;
  scope: "shortlist" | "opening";
  expires_at: string;
  candidates: SharedCandidate[];
}

export function Shared({ token }: { token: string }) {
  const [view, setView] = useState<SharedView | null>(null);
  const [gone, setGone] = useState(false);
  const [open, setOpen] = useState<string | null>(null);

  useEffect(() => {
    fetch(`/api/v1/shared/${encodeURIComponent(token)}`)
      .then((r) => (r.ok ? r.json() : Promise.reject()))
      .then((body: SharedView) => {
        setView(body);
        setOpen(body.candidates[0]?.id ?? null);
        document.title = `${body.opening_title} · shortlist`;
      })
      .catch(() => setGone(true));
  }, [token]);

  if (gone) {
    return (
      <div className="gate">
        <div style={{ maxWidth: 400 }}>
          <h1 className="wordmark">This link is not available</h1>
          <p className="lede">
            It may have expired or been withdrawn. Ask whoever sent it for a new one.
          </p>
        </div>
      </div>
    );
  }
  if (!view) return <p className="empty">Loading…</p>;

  const expires = new Date(view.expires_at).toLocaleDateString("en-GB", {
    day: "numeric",
    month: "long",
  });

  return (
    <div className="shared">
      <header className="shared-top">
        <div>
          <p className="shared-company">{view.company_name}</p>
          <h1 className="shared-role">{view.opening_title}</h1>
        </div>
        <p className="shared-meta">
          {view.candidates.length} shortlisted · read-only · expires {expires}
        </p>
      </header>

      {view.candidates.length === 0 ? (
        <p className="empty">
          <strong>Nobody has been shortlisted yet</strong>
          This link will show the shortlist as soon as there is one.
        </p>
      ) : (
        <ol className="shared-list">
          {view.candidates.map((candidate, index) => (
            <li key={candidate.id}>
              <button
                className="shared-row"
                aria-expanded={open === candidate.id}
                onClick={() => setOpen(open === candidate.id ? null : candidate.id)}
              >
                <span className="num shared-rank">{String(index + 1).padStart(2, "0")}</span>
                <span className="shared-name">
                  {candidate.name}
                  {candidate.tampered && (
                    <span className="mark found" style={{ marginLeft: 8 }}>
                      concealed text
                    </span>
                  )}
                  {!candidate.mandatory_requirements_met && (
                    <span className="mark" style={{ marginLeft: 8 }}>
                      missing must-haves
                    </span>
                  )}
                </span>
                <span className="num shared-score">
                  {Number(candidate.overall_score).toFixed(0)}
                </span>
              </button>

              {open === candidate.id && <Detail candidate={candidate} token={token} />}
            </li>
          ))}
        </ol>
      )}

      <footer className="shared-foot">
        Scores are computed from the rubric this company wrote. Every quote below a score was
        checked against the résumé before it was shown, and a person made every decision.
      </footer>
    </div>
  );
}

function Detail({ candidate, token }: { candidate: SharedCandidate; token: string }) {
  const [pages, setPages] = useState(false);
  const [active, setActive] = useState<string | null>(null);
  const evidence: Evidence[] = candidate.criteria.flatMap((c) => c.evidence);

  return (
    <div className="shared-detail">
      <p className="shared-summary">{candidate.summary}</p>
      <p className="hint">
        {Number(candidate.relevant_years_experience)} years relevant
        {candidate.detected_skills.length > 0 &&
          ` · ${candidate.detected_skills.slice(0, 6).join(", ")}`}
      </p>

      {candidate.criteria.map((criterion) => (
        <div className="shared-finding" key={criterion.criterion_id}>
          <div className="finding-head">
            <span className="finding-name">{criterion.criterion_name}</span>
            <span className="finding-weight">weight {criterion.weight}</span>
            <span className="finding-score">{criterion.score}/5</span>
          </div>
          {criterion.justification && <p className="finding-why">{criterion.justification}</p>}
          {criterion.evidence.map((item, i) => (
            <button
              key={i}
              className={`locator${item.found ? "" : " unverified"}`}
              onMouseEnter={() => item.found && setActive(item.quote)}
              onMouseLeave={() => setActive(null)}
            >
              {item.found ? `“${item.quote}”` : `Not in the document: “${item.quote}”`}
            </button>
          ))}
        </div>
      ))}

      <div className="registers" style={{ marginTop: 16 }}>
        <button className="control" aria-pressed={!pages} onClick={() => setPages(false)}>
          Transcript
        </button>
        <button className="control" aria-pressed={pages} onClick={() => setPages(true)}>
          Document
        </button>
      </div>

      {pages ? (
        <div className="pages">
          {Array.from({ length: Math.max(candidate.page_count, 1) }, (_, i) => (
            <img
              key={i}
              src={`/api/v1/shared/${encodeURIComponent(token)}/candidates/${candidate.id}/pages/${i + 1}`}
              alt={`Page ${i + 1}`}
              loading="lazy"
            />
          ))}
        </div>
      ) : (
        <div className="transcript">
          {segment(candidate.resume_text, evidence).map((part, i) =>
            part.highlighted ? (
              <mark key={i} data-active={part.quote === active}>
                {part.text}
              </mark>
            ) : (
              <span key={i}>{part.text}</span>
            ),
          )}
        </div>
      )}
    </div>
  );
}
