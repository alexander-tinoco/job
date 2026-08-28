import type { ApplicationDetail } from "../lib/types";

/**
 * Two kinds of warning, deliberately not mixed.
 *
 * `risks` are observations about the candidate, made by the model.
 * `review_flags` are objections raised by our own verification — an unfound
 * quote means our evaluation has a problem, not the person. Presenting them
 * together would invite exactly the wrong reading.
 */
export function Flags({ detail }: { detail: ApplicationDetail }) {
  const integrity = detail.integrity;
  const tampered = integrity && integrity.verdict !== "clean";

  if (!tampered && detail.risks.length === 0 && detail.review_flags.length === 0) {
    return null;
  }

  return (
    <section>
      <h3>Flags</h3>

      {tampered && integrity && (
        <div className="notice bad">
          <strong>
            {integrity.verdict === "tampered"
              ? "This résumé hides text from human readers."
              : "This résumé looks suspicious."}
          </strong>
          <p style={{ margin: "6px 0 0" }}>
            The hidden text below was removed before anything was evaluated. The
            score comes from the visible text only.
          </p>
          {integrity.hidden_spans.length > 0 && (
            <ul>
              {integrity.hidden_spans.map((span, index) => (
                <li key={index}>
                  <code>{span.reason}</code> ({span.detail}, page {span.page}):{" "}
                  {span.text.slice(0, 220)}
                </li>
              ))}
            </ul>
          )}
          {integrity.matched_patterns.length > 0 && (
            <p style={{ margin: "6px 0 0" }}>
              Patterns matched: {integrity.matched_patterns.join(", ")}
            </p>
          )}
        </div>
      )}

      {detail.risks.length > 0 && (
        <div className="notice info">
          <strong>Noted about the candidate</strong>
          <ul>
            {detail.risks.map((risk, index) => (
              <li key={index}>{risk}</li>
            ))}
          </ul>
        </div>
      )}

      {detail.review_flags.length > 0 && (
        <div className="notice info">
          <strong>Our evaluation needs a human look</strong>
          <p style={{ margin: "6px 0 0" }}>
            These are objections to the evaluation, not to the candidate.
          </p>
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
