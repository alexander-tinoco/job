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
  onSelect,
}: {
  item: ApplicationSummary;
  rank: number;
  selected: boolean;
  onSelect: (id: string) => void;
}) {
  const scored = item.overall_score !== null;
  return (
    <button className="exhibit" aria-current={selected} onClick={() => onSelect(item.id)}>
      <span className="exhibit-rank">{scored ? String(rank).padStart(2, "0") : "—"}</span>

      <span>
        <span className="exhibit-name">{item.candidate_name}</span>
        <span className="exhibit-sub">{item.candidate_email}</span>
        {(item.integrity === "tampered" ||
          item.needs_human_review ||
          item.mandatory_requirements_met === false ||
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
