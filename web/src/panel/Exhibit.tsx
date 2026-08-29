import { DecidedIcon, LocatedIcon, UnverifiedIcon } from "../components/icons";
import type { ApplicationSummary } from "../lib/types";

/** Never a time. The batch window is 24 h and not configurable. */
const PENDING: Record<ApplicationSummary["state"], string> = {
  received: "Reading the file",
  extracted: "Awaiting examination",
  queued: "Under examination",
  evaluated: "",
  error: "Could not be read",
};

export function Exhibit({
  item,
  rank,
  selected,
  picking,
  onSelect,
}: {
  item: ApplicationSummary;
  rank: number;
  selected: boolean;
  /** While picking, an unexamined candidate has no scores to line up. */
  picking?: boolean;
  onSelect: (id: string) => void;
}) {
  const scored = item.overall_score !== null;
  return (
    <button
      className={picking ? "exhibit picking" : "exhibit"}
      aria-current={selected}
      aria-pressed={picking ? selected : undefined}
      disabled={picking && !scored}
      onClick={() => onSelect(item.id)}
    >
      <span className="exhibit-rank">{scored ? String(rank).padStart(2, "0") : "—"}</span>

      <span>
        <span className="exhibit-name">{item.candidate_name}</span>
        <span className="exhibit-sub">{item.candidate_email}</span>
        {(item.integrity === "tampered" ||
          item.needs_human_review ||
          item.mandatory_requirements_met === false ||
          item.unmet_requirements.length > 0 ||
          item.decision) && (
          <span className="exhibit-marks">
            {item.integrity === "tampered" && (
              <span className="mark found">
                <LocatedIcon /> concealed text
              </span>
            )}
            {item.needs_human_review && (
              <span className="mark unverified">
                <UnverifiedIcon /> unverified claim
              </span>
            )}
            {item.mandatory_requirements_met === false && (
              <span className="mark">missing must-haves</span>
            )}
            {/* Distinct from "missing must-haves" above, which is the model
                reading the résumé. This is the applicant's own answer. */}
            {item.unmet_requirements.length > 0 && (
              // A label like its neighbours, not the question itself: the
              // questions are on the candidate's page and in the tooltip.
              <span className="mark stated" title={item.unmet_requirements.join(" · ")}>
                said no to{" "}
                {item.unmet_requirements.length === 1
                  ? "a requirement"
                  : `${item.unmet_requirements.length} requirements`}
              </span>
            )}
            {item.decision && (
              <span className="mark decided">
                <DecidedIcon /> {item.decision.kind === "shortlist" ? "shortlisted" : "declined"}
              </span>
            )}
          </span>
        )}
      </span>

      {scored ? (
        <span className="exhibit-score num">{Number(item.overall_score).toFixed(0)}</span>
      ) : (
        <span className="exhibit-pending">{PENDING[item.state]}</span>
      )}
    </button>
  );
}
