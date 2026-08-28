import { useCallback, useEffect, useMemo, useState } from "react";
import { CandidateDetail } from "./components/CandidateDetail";
import { CandidateRow } from "./components/CandidateRow";
import { Unauthorized, api, clearToken, getToken, setToken } from "./lib/api";
import type { ApplicationDetail, Opening, RankedPage } from "./lib/types";

type Filter = "all" | "unreviewed" | "flagged" | "shortlisted";

function TokenGate({ onDone }: { onDone: () => void }) {
  const [value, setValue] = useState("");
  return (
    <div className="gate">
      <h1>Candidate Screening</h1>
      <p>
        Enter the admin token for this deployment. It is stored in this browser
        only.
      </p>
      <input
        type="password"
        value={value}
        placeholder="Admin token"
        onChange={(event) => setValue(event.target.value)}
        onKeyDown={(event) => {
          if (event.key === "Enter" && value.trim()) {
            setToken(value.trim());
            onDone();
          }
        }}
      />
      <button
        className="btn"
        disabled={!value.trim()}
        onClick={() => {
          setToken(value.trim());
          onDone();
        }}
      >
        Open the panel
      </button>
    </div>
  );
}

export default function App() {
  const [authed, setAuthed] = useState(() => getToken() !== null);
  const [openings, setOpenings] = useState<Opening[]>([]);
  const [openingId, setOpeningId] = useState<string | null>(null);
  const [page, setPage] = useState<RankedPage | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [detail, setDetail] = useState<ApplicationDetail | null>(null);
  const [filter, setFilter] = useState<Filter>("all");
  const [query, setQuery] = useState("");
  const [matches, setMatches] = useState<Set<string> | null>(null);
  const [error, setError] = useState<string | null>(null);

  const fail = useCallback((caught: unknown) => {
    if (caught instanceof Unauthorized) {
      clearToken();
      setAuthed(false);
      return;
    }
    setError(caught instanceof Error ? caught.message : String(caught));
  }, []);

  useEffect(() => {
    if (!authed) return;
    api
      .openings()
      .then((list) => {
        setOpenings(list);
        setOpeningId((current) => current ?? list[0]?.id ?? null);
      })
      .catch(fail);
  }, [authed, fail]);

  const reload = useCallback(() => {
    if (!openingId) return;
    api.ranked(openingId).then(setPage).catch(fail);
  }, [openingId, fail]);

  useEffect(reload, [reload]);

  useEffect(() => {
    if (!selected) {
      setDetail(null);
      return;
    }
    api.detail(selected).then(setDetail).catch(fail);
  }, [selected, fail]);

  // Search narrows the ranking rather than replacing it, so the ordering the
  // panel exists to show is never lost.
  useEffect(() => {
    const term = query.trim();
    if (!openingId || term.length < 2) {
      setMatches(null);
      return;
    }
    const timer = setTimeout(() => {
      api
        .search(openingId, term)
        .then((result) => setMatches(new Set(result.hits.map((h) => h.application_id))))
        .catch(fail);
    }, 250);
    return () => clearTimeout(timer);
  }, [query, openingId, fail]);

  const visible = useMemo(() => {
    const items = page?.items ?? [];
    return items.filter((item) => {
      if (matches && !matches.has(item.id)) return false;
      if (filter === "unreviewed") return item.decision === null;
      if (filter === "flagged") {
        return (
          item.needs_human_review ||
          (item.integrity !== null && item.integrity !== "clean")
        );
      }
      if (filter === "shortlisted") return item.decision?.kind === "shortlist";
      return true;
    });
  }, [page, filter, matches]);

  if (!authed) return <TokenGate onDone={() => setAuthed(true)} />;

  return (
    <div className="app">
      <div className="column list">
        <div className="bar">
          <h1>{page?.opening_title ?? "Candidates"}</h1>
          <select
            value={openingId ?? ""}
            onChange={(event) => {
              setOpeningId(event.target.value);
              setSelected(null);
            }}
          >
            {openings.map((opening) => (
              <option key={opening.id} value={opening.id}>
                {opening.title}
              </option>
            ))}
          </select>
          <select
            value={filter}
            onChange={(event) => setFilter(event.target.value as Filter)}
          >
            <option value="all">Everyone</option>
            <option value="unreviewed">Not yet decided</option>
            <option value="flagged">Flagged</option>
            <option value="shortlisted">Shortlisted</option>
          </select>
          <input
            placeholder="Search résumés…"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
          />
          {page && (
            <span className="count">
              {visible.length} of {page.total} · {page.evaluated} evaluated
              {page.evaluated < page.total &&
                ` · ${page.total - page.evaluated} still being evaluated`}
            </span>
          )}
        </div>

        {error && <p className="error" style={{ padding: "12px 16px" }}>{error}</p>}

        {visible.map((item) => (
          <CandidateRow
            key={item.id}
            item={item}
            selected={item.id === selected}
            onSelect={setSelected}
          />
        ))}

        {page && visible.length === 0 && (
          <p className="empty">No candidates match this view.</p>
        )}
      </div>

      <div className="column">
        {detail ? (
          <CandidateDetail
            detail={detail}
            onDecided={() => {
              reload();
              api.detail(detail.id).then(setDetail).catch(fail);
            }}
          />
        ) : (
          <p className="empty">Select a candidate.</p>
        )}
      </div>
    </div>
  );
}
