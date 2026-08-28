import { UnverifiedIcon } from "../components/icons";
import type { Comparison as Result } from "../lib/types";

const MAX_SCORE = 5;

/**
 * Two or three candidates in columns.
 *
 * The screen exists for one sentence: *where does the difference come from*.
 * Because the overall score is a weighted sum, the gap decomposes exactly, so
 * each row can say how many points of the total it is worth — and one row is
 * usually the whole answer.
 */
export function Comparison({ result }: { result: Result }) {
  const columns = result.candidates.length;
  const ahead = result.candidates.reduce((best, one) =>
    Number(one.overall_score) > Number(best.overall_score) ? one : best,
  );
  const gap = (
    Number(ahead.overall_score) -
    Math.min(...result.candidates.map((one) => Number(one.overall_score)))
  ).toFixed(0);

  return (
    <div className="compare" style={{ "--cols": columns } as React.CSSProperties}>
      <div className="compare-head">
        <span className="compare-label">Criterion</span>
        {result.candidates.map((one) => (
          <div key={one.id} className="compare-who">
            <span className="compare-name">{one.name}</span>
            <span className="compare-total num">{Number(one.overall_score).toFixed(0)}</span>
            <span className="compare-marks">
              {one.tampered && (
                <span className="mark found">concealed text</span>
              )}
              {!one.mandatory_requirements_met && (
                <span className="mark">missing must-haves</span>
              )}
              {one.decision && (
                <span className="mark decided">
                  {one.decision === "shortlist" ? "shortlisted" : "declined"}
                </span>
              )}
            </span>
          </div>
        ))}
      </div>

      <p className="compare-verdict">
        {result.decisive.length === 0 ? (
          <>
            These candidates scored <strong>identically on every criterion</strong>. Nothing in
            the rubric separates them — whatever decides this is not on this screen.
          </>
        ) : (
          <>
            <strong>{ahead.name}</strong> leads by <span className="num">{gap}</span>{" "}
            {gap === "1" ? "point" : "points"}. The difference is
            {/* Chips, not prose: a criterion may itself be called "SQL and data
                modelling", and joining those with "and" makes one name of two. */}
            {result.decisive.map((name) => (
              <span key={name} className="compare-decisive">
                {name}
              </span>
            ))}
          </>
        )}
      </p>

      {result.criteria.map((row) => (
        <div key={row.criterion_id} className="compare-row">
          <div className="compare-label">
            <span className="compare-criterion">{row.criterion_name}</span>
            <span className="compare-weight num">{row.weight}%</span>
            {row.mandatory && <span className="mark">must have</span>}
            {Number(row.spread) > 0 && (
              <span className="compare-spread">
                worth <span className="num">{Number(row.spread).toFixed(0)}</span> of the gap
              </span>
            )}
          </div>

          {row.sides.map((side) => {
            const leads = row.leaders.includes(side.application_id);
            return (
              <div
                key={side.application_id}
                className={leads ? "compare-cell leads" : "compare-cell"}
              >
                <span className="compare-score">
                  <span className="num">{side.score}</span>
                  <span className="compare-of">/{MAX_SCORE}</span>
                  <span className="compare-bar" aria-hidden="true">
                    <span style={{ width: `${(side.score / MAX_SCORE) * 100}%` }} />
                  </span>
                </span>
                <p className="compare-why">{side.justification}</p>
                {side.quotes.length > 0 ? (
                  side.quotes.map((quote) => (
                    <blockquote key={quote} className="compare-quote">
                      {quote}
                    </blockquote>
                  ))
                ) : (
                  <p className="compare-nothing">
                    <UnverifiedIcon /> nothing in the résumé backs this
                  </p>
                )}
              </div>
            );
          })}
        </div>
      ))}
    </div>
  );
}
