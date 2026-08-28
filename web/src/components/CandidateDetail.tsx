import { useState } from "react";
import { api } from "../lib/api";
import type { ApplicationDetail, DecisionKind } from "../lib/types";
import { Flags } from "./Flags";
import { ResumeText } from "./ResumeText";

export function CandidateDetail({
  detail,
  onDecided,
}: {
  detail: ApplicationDetail;
  onDecided: () => void;
}) {
  const [reason, setReason] = useState("");
  const [by, setBy] = useState(() => localStorage.getItem("screening.who") ?? "");
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  const allEvidence = detail.criteria.flatMap((c) => c.evidence);

  async function decide(kind: DecisionKind) {
    setSaving(true);
    setError(null);
    try {
      await api.decide(detail.id, kind, reason.trim(), by.trim());
      localStorage.setItem("screening.who", by.trim());
      setReason("");
      onDecided();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : String(caught));
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="detail">
      <h2>{detail.candidate_name}</h2>
      <p className="contact">
        {detail.candidate_email}
        {detail.candidate_phone ? ` · ${detail.candidate_phone}` : ""}
        {detail.candidate_linkedin ? ` · ${detail.candidate_linkedin}` : ""}
      </p>

      {detail.overall_score === null ? (
        <div className="notice info">
          Evaluation in progress. The résumé and its flags are already available
          below.
        </div>
      ) : (
        <>
          <div className="headline">
            <span className="big">{Number(detail.overall_score).toFixed(0)}</span>
            <span className="chip">
              {detail.mandatory_requirements_met
                ? "meets must-haves"
                : "missing must-haves"}
            </span>
            {detail.relevant_years_experience !== null && (
              <span className="chip">
                {Number(detail.relevant_years_experience)} yrs relevant
              </span>
            )}
          </div>
          <p style={{ marginTop: 4 }}>{detail.summary}</p>
        </>
      )}

      <Flags detail={detail} />

      {detail.criteria.length > 0 && (
        <section>
          <h3>Scores</h3>
          {detail.criteria.map((criterion) => (
            <div className="criterion" key={criterion.criterion_id}>
              <div className="criterion-top">
                <span className="criterion-name">
                  {criterion.criterion_name}
                  {criterion.mandatory && (
                    <span className="chip" style={{ marginLeft: 6 }}>
                      required
                    </span>
                  )}
                </span>
                <span className="criterion-score">
                  {criterion.score}/5 · weight {criterion.weight}
                </span>
              </div>
              <p>{criterion.justification}</p>
              {criterion.evidence.map((item, index) => (
                <p
                  className={`quote${item.found ? "" : " unverified"}`}
                  key={index}
                >
                  {item.found
                    ? `“${item.quote}”`
                    : `Not found in the résumé: “${item.quote}”`}
                </p>
              ))}
            </div>
          ))}
        </section>
      )}

      {detail.missing_requirements.length > 0 && (
        <section>
          <h3>Missing</h3>
          <p>{detail.missing_requirements.join(", ")}</p>
        </section>
      )}

      <section>
        <h3>Résumé text — quoted passages highlighted</h3>
        <ResumeText text={detail.resume_text} evidence={allEvidence} />
        <p style={{ marginTop: 8, fontSize: 13 }}>
          <a href={api.resumeUrl(detail.id)}>Download the original PDF</a>{" "}
          <span style={{ color: "var(--muted)" }}>
            ({detail.page_count} page{detail.page_count === 1 ? "" : "s"})
          </span>
        </p>
      </section>

      <section>
        <h3>Decision</h3>
        {detail.decision ? (
          <div className="notice info">
            <strong>
              {detail.decision.kind === "shortlist" ? "Shortlisted" : "Rejected"}
            </strong>{" "}
            by {detail.decision.decided_by} — {detail.decision.reason}
          </div>
        ) : (
          <>
            <div className="actions">
              <input
                placeholder="Your name or email"
                value={by}
                onChange={(event) => setBy(event.target.value)}
              />
            </div>
            <div className="actions">
              <input
                placeholder="Why? (recorded in the audit log)"
                value={reason}
                onChange={(event) => setReason(event.target.value)}
              />
              <button
                className="btn good"
                disabled={saving || !reason.trim() || !by.trim()}
                onClick={() => decide("shortlist")}
              >
                Shortlist
              </button>
              <button
                className="btn bad"
                disabled={saving || !reason.trim() || !by.trim()}
                onClick={() => decide("reject")}
              >
                Reject
              </button>
            </div>
            {error && <p className="error">{error}</p>}
          </>
        )}
      </section>

      {detail.model_id && (
        <p className="provenance">
          Scored by {detail.model_id}, prompt {detail.prompt_version}, rubric
          version {detail.rubric_version}. The model rated each criterion; the
          overall score was computed from the rubric weights.
        </p>
      )}
    </div>
  );
}
