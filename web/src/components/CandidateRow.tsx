import type { ApplicationSummary } from "../lib/types";

const STATE_LABEL: Record<ApplicationSummary["state"], string> = {
  received: "Uploaded",
  extracted: "Evaluation in progress",
  queued: "Evaluation in progress",
  evaluated: "Evaluated",
  error: "Needs attention",
};

export function CandidateRow({
  item,
  selected,
  onSelect,
}: {
  item: ApplicationSummary;
  selected: boolean;
  onSelect: (id: string) => void;
}) {
  return (
    <button
      className="row"
      aria-current={selected}
      onClick={() => onSelect(item.id)}
    >
      <span className="row-top">
        <span className="row-name">{item.candidate_name}</span>
        {item.overall_score === null ? (
          // Never a time: the batch window is 24 h and not configurable.
          <span className="score pending">{STATE_LABEL[item.state]}</span>
        ) : (
          <span className="score">{Number(item.overall_score).toFixed(0)}</span>
        )}
      </span>
      <span className="row-sub">{item.candidate_email}</span>
      <span className="chips">
        {item.integrity === "tampered" && (
          <span className="chip tampered">hidden text</span>
        )}
        {item.integrity === "suspicious" && (
          <span className="chip suspicious">suspicious</span>
        )}
        {item.mandatory_requirements_met === false && (
          <span className="chip suspicious">missing must-haves</span>
        )}
        {item.needs_human_review && <span className="chip review">needs review</span>}
        {item.decision && (
          <span className={`chip ${item.decision.kind}`}>{item.decision.kind}</span>
        )}
      </span>
    </button>
  );
}
