import { useState } from "react";
import { LocatedIcon, UnverifiedIcon } from "../components/icons";
import { api } from "../lib/api";
import type { ApplicationDetail, DecisionKind } from "../lib/types";
import { DocumentPlate } from "./Document";

export function Plate({
  detail,
  onChanged,
}: {
  detail: ApplicationDetail;
  onChanged: () => void;
}) {
  // The raking light: focusing a finding lifts its quote in the document.
  const [activeQuote, setActiveQuote] = useState<string | null>(null);
  const evidence = detail.criteria.flatMap((criterion) => criterion.evidence);
  const scored = detail.overall_score !== null;

  return (
    <div className="plate">
      <header className="plate-head">
        <h1 className="plate-name">{detail.candidate_name}</h1>
        <p className="plate-contact">
          <a href={`mailto:${detail.candidate_email}`}>{detail.candidate_email}</a>
          {detail.candidate_phone && ` · ${detail.candidate_phone}`}
          {detail.candidate_linkedin && (
            <>
              {" · "}
              <a href={detail.candidate_linkedin} rel="noreferrer noopener" target="_blank">
                LinkedIn
              </a>
            </>
          )}
        </p>

        {scored ? (
          <>
            <div className="verdict">
              <span className="verdict-score">{Number(detail.overall_score).toFixed(0)}</span>
              <span className="verdict-of">
                of 100, from the rubric weights
                {detail.relevant_years_experience !== null &&
                  ` · ${Number(detail.relevant_years_experience)} years relevant`}
                {detail.mandatory_requirements_met === false && " · missing must-haves"}
              </span>
            </div>
            {detail.summary && <p className="plate-summary">{detail.summary}</p>}
          </>
        ) : (
          <NotYetExamined detail={detail} onChanged={onChanged} />
        )}
      </header>

      <Concealed detail={detail} />
      <Objections detail={detail} />

      {detail.criteria.length > 0 && (
        <section className="section">
          <h2>Findings</h2>
          {detail.criteria.map((criterion, index) => (
            <article className="finding" key={criterion.criterion_id}>
              <span className="finding-index">{String(index + 1).padStart(2, "0")}</span>
              <div>
                <div className="finding-head">
                  <span
                    className="finding-name"
                    /* Weight sets size: the layout obeys the rubric, not a grid. */
                    style={{ fontSize: `${13 + criterion.weight / 12}px` }}
                  >
                    {criterion.criterion_name}
                  </span>
                  <span className="finding-weight">
                    weight {criterion.weight}
                    {criterion.mandatory && " · required"}
                  </span>
                  <span className="finding-score">{criterion.score}/5</span>
                </div>
                {criterion.justification && (
                  <p className="finding-why">{criterion.justification}</p>
                )}
                {criterion.evidence.map((item, position) => (
                  <button
                    key={position}
                    className={`locator${item.found ? "" : " unverified"}`}
                    aria-current={item.quote === activeQuote}
                    onMouseEnter={() => item.found && setActiveQuote(item.quote)}
                    onFocus={() => item.found && setActiveQuote(item.quote)}
                    onMouseLeave={() => setActiveQuote(null)}
                    onBlur={() => setActiveQuote(null)}
                  >
                    {item.found ? (
                      <>
                        “{item.quote}”
                        <span className="offset">
                          at {item.start}–{item.end}
                        </span>
                      </>
                    ) : (
                      <>Not present in the document: “{item.quote}”</>
                    )}
                  </button>
                ))}
              </div>
            </article>
          ))}
        </section>
      )}

      {detail.missing_requirements.length > 0 && (
        <section className="section">
          <h2>Not evidenced</h2>
          <p className="finding-why">{detail.missing_requirements.join(" · ")}</p>
        </section>
      )}

      <section className="section">
        <h2>The document</h2>
        <DocumentPlate
          applicationId={detail.id}
          text={detail.resume_text}
          evidence={evidence}
          pageCount={detail.page_count}
          activeQuote={activeQuote}
        />
      </section>

      <Decision detail={detail} onChanged={onChanged} />

      {detail.model_id && (
        <p className="provenance">
          Examined by <span className="num">{detail.model_id}</span>, prompt{" "}
          <span className="num">{detail.prompt_version}</span>, rubric version{" "}
          <span className="num">{detail.rubric_version}</span>. The model rated each criterion
          against the résumé and quoted its evidence; the score above was computed from the
          rubric weights, not written by the model. Every quote was checked against the
          document before it was shown.
        </p>
      )}
    </div>
  );
}

function NotYetExamined({
  detail,
  onChanged,
}: {
  detail: ApplicationDetail;
  onChanged: () => void;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const ready = detail.resume_text.trim().length > 0;

  return (
    <div style={{ marginTop: 16 }}>
      <p className="plate-summary" style={{ margin: 0 }}>
        {ready
          ? "This application is queued for the next examination round. The document below is already available."
          : "Nothing could be read from this file, so it cannot be examined."}
      </p>
      {ready && (
        <div style={{ marginTop: 12 }}>
          <button
            className="control"
            disabled={busy}
            onClick={async () => {
              setBusy(true);
              setError(null);
              try {
                await api.evaluateNow(detail.id);
                onChanged();
              } catch (caught) {
                setError(caught instanceof Error ? caught.message : String(caught));
              } finally {
                setBusy(false);
              }
            }}
          >
            {busy ? "Examining…" : "Examine now"}
          </button>
          <p className="hint">
            Runs this one candidate immediately instead of waiting for the batch.
          </p>
          {error && <p className="notice-error">{error}</p>}
        </div>
      )}
    </div>
  );
}

function Concealed({ detail }: { detail: ApplicationDetail }) {
  const integrity = detail.integrity;
  if (!integrity || integrity.verdict === "clean") return null;

  return (
    <section className="section">
      <h2>Concealed layer</h2>
      <div className="concealed">
        <h3>
          <LocatedIcon />{" "}
          {integrity.verdict === "tampered"
            ? "This document hides text from human readers"
            : "This document looks irregular"}
        </h3>
        <p>
          The passages below were present in the file but invisible on the page. They were
          removed before anything was examined, and the score was computed from the visible
          text alone.
        </p>
        {integrity.hidden_spans.length > 0 && (
          <ol>
            {integrity.hidden_spans.map((span, index) => (
              <li key={index}>
                {span.text.slice(0, 260)}
                <span className="where">
                  {span.reason} · {span.detail} · page {span.page}
                </span>
              </li>
            ))}
          </ol>
        )}
      </div>
    </section>
  );
}

function Objections({ detail }: { detail: ApplicationDetail }) {
  if (detail.risks.length === 0 && detail.review_flags.length === 0) return null;

  return (
    <section className="section">
      <h2>Notes</h2>
      {detail.risks.length > 0 && (
        <div className="objection" style={{ marginBottom: 10 }}>
          <h3>Observed in the candidate</h3>
          <ul>
            {detail.risks.map((risk, index) => (
              <li key={index}>{risk}</li>
            ))}
          </ul>
        </div>
      )}
      {detail.review_flags.length > 0 && (
        <div className="objection">
          <h3>
            <UnverifiedIcon /> Our examination needs a human look
          </h3>
          <p>These are objections to the evaluation, not to the candidate.</p>
          <ul>
            {detail.review_flags.map((flag, index) => (
              <li key={index}>{flag}</li>
            ))}
          </ul>
        </div>
      )}
    </section>
  );
}

function Decision({
  detail,
  onChanged,
}: {
  detail: ApplicationDetail;
  onChanged: () => void;
}) {
  const [reason, setReason] = useState("");
  const [by, setBy] = useState(() => localStorage.getItem("verbatim.who") ?? "");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function decide(kind: DecisionKind) {
    setBusy(true);
    setError(null);
    try {
      await api.decide(detail.id, kind, reason.trim(), by.trim());
      localStorage.setItem("verbatim.who", by.trim());
      setReason("");
      onChanged();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : String(caught));
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="section">
      <h2>Decision</h2>
      {detail.decision ? (
        <div className="decided">
          <strong>
            {detail.decision.kind === "shortlist" ? "Shortlisted" : "Declined"} by{" "}
            {detail.decision.decided_by}
          </strong>
          <p>{detail.decision.reason}</p>
        </div>
      ) : (
        <div className="decision-form">
          <input
            className="field"
            placeholder="Your name"
            value={by}
            onChange={(event) => setBy(event.target.value)}
          />
          <div className="decision-row">
            <input
              className="field"
              placeholder="Why — recorded alongside the score"
              value={reason}
              onChange={(event) => setReason(event.target.value)}
            />
            <button
              className="control primary"
              disabled={busy || !reason.trim() || !by.trim()}
              onClick={() => decide("shortlist")}
            >
              Shortlist
            </button>
            <button
              className="control"
              disabled={busy || !reason.trim() || !by.trim()}
              onClick={() => decide("reject")}
            >
              Decline
            </button>
          </div>
          <p className="hint">
            The decision is yours and is recorded with your reason. It never replaces the
            examination; both are kept.
          </p>
          {error && <p className="notice-error">{error}</p>}
        </div>
      )}
    </section>
  );
}
