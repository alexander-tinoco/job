import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Confirm } from "../components/Confirm";
import {
  CollapseIcon,
  CompareIcon,
  ExpandIcon,
  ShareIcon,
  SignOutIcon,
} from "../components/icons";
import type { User } from "../lib/api";
import { Unauthorized, api } from "../lib/api";
import type { ApplicationDetail, Comparison as Result, Opening, RankedPage } from "../lib/types";
import { Comparison } from "./Comparison";
import { Exhibit } from "./Exhibit";
import { Plate } from "./Plate";

type Filter = "all" | "open" | "flagged" | "shortlisted";

/** Three columns is already more than anyone reads at once. */
const MAX_COMPARED = 3;

const FILTERS: { id: Filter; label: string }[] = [
  { id: "all", label: "Everyone" },
  { id: "open", label: "Undecided" },
  { id: "flagged", label: "Flagged" },
  { id: "shortlisted", label: "Shortlisted" },
];

export function Panel({ me, onSignedOut }: { me: User; onSignedOut: () => void }) {
  const [openings, setOpenings] = useState<Opening[]>([]);
  const [openingId, setOpeningId] = useState<string | null>(null);
  const [page, setPage] = useState<RankedPage | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [detail, setDetail] = useState<ApplicationDetail | null>(null);
  const [filter, setFilter] = useState<Filter>("all");
  const [query, setQuery] = useState("");
  const [matches, setMatches] = useState<Set<string> | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [focused, setFocused] = useState(false);
  const [confirmingSignOut, setConfirmingSignOut] = useState(false);
  const [shareUrl, setShareUrl] = useState<string | null>(null);
  const [sharing, setSharing] = useState(false);
  // `null` is the ordinary panel. An array — even an empty one — means the list
  // is picking candidates to line up rather than opening them.
  const [picked, setPicked] = useState<string[] | null>(null);
  const [comparison, setComparison] = useState<Result | null>(null);
  const plate = useRef<HTMLDivElement>(null);

  const fail = useCallback(
    (caught: unknown) => {
      if (caught instanceof Unauthorized) {
        onSignedOut();
        return;
      }
      setError(caught instanceof Error ? caught.message : String(caught));
    },
    [onSignedOut],
  );

  useEffect(() => {
    api
      .openings()
      .then((list) => {
        setOpenings(list);
        setOpeningId((current) => current ?? list[0]?.id ?? null);
      })
      .catch(fail);
  }, [fail]);

  const reload = useCallback(() => {
    if (!openingId) return;
    api.ranked(openingId).then(setPage).catch(fail);
  }, [openingId, fail]);

  useEffect(reload, [reload]);

  const reloadDetail = useCallback(() => {
    if (!selected) {
      setDetail(null);
      return;
    }
    api.detail(selected).then(setDetail).catch(fail);
  }, [selected, fail]);

  useEffect(reloadDetail, [reloadDetail]);

  // Two is the point at which a comparison exists; below that there is nothing
  // to line up, so the fetch simply does not happen.
  useEffect(() => {
    if (!openingId || picked === null || picked.length < 2) {
      setComparison(null);
      return;
    }
    api.compare(openingId, picked).then(setComparison).catch(fail);
  }, [openingId, picked, fail]);

  const pick = useCallback((id: string) => {
    setPicked((current) => {
      if (current === null) return current;
      if (current.includes(id)) return current.filter((one) => one !== id);
      // Silently dropping the click would look broken, so the oldest column
      // gives way to the newest.
      return [...current, id].slice(-MAX_COMPARED);
    });
  }, []);

  // Each application opens at its own beginning. Landing halfway down the
  // previous candidate's page is how a reviewer misses the summary entirely.
  useEffect(() => {
    plate.current?.scrollTo({ top: 0 });
  }, [selected]);

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
        .then((result) => setMatches(new Set(result.hits.map((hit) => hit.application_id))))
        .catch(fail);
    }, 220);
    return () => clearTimeout(timer);
  }, [query, openingId, fail]);

  const visible = useMemo(() => {
    const items = page?.items ?? [];
    return items.filter((item) => {
      if (matches && !matches.has(item.id)) return false;
      if (filter === "open") return item.decision === null;
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

  const waiting = page ? page.total - page.evaluated : 0;

  return (
    <div className={focused ? "bench focused" : "bench"}>
      {focused && (
        <button className="reopen" onClick={() => setFocused(false)}>
          <ExpandIcon /> Show the list
        </button>
      )}

      <div className="register exhibits">
        <div className="masthead">
          <div className="masthead-top">
            <span className="wordmark-sm">Verbatim</span>
            <span className="spacer" />
            <button
              className="control quiet"
              title="Create a read-only link to the shortlist"
              aria-label="Share the shortlist"
              disabled={!openingId || sharing}
              onClick={async () => {
                if (!openingId) return;
                setSharing(true);
                try {
                  const made = await api.share(openingId);
                  setShareUrl(`${window.location.origin}${made.url_path}`);
                } catch (caught) {
                  fail(caught);
                } finally {
                  setSharing(false);
                }
              }}
            >
              <ShareIcon />
            </button>
            <button
              className="control quiet"
              title="Line two candidates up side by side"
              aria-label="Compare candidates"
              aria-pressed={picked !== null}
              onClick={() => setPicked((current) => (current === null ? [] : null))}
            >
              <CompareIcon />
            </button>
            <button
              className="control quiet"
              title="Hide the list and read one application"
              aria-label="Hide the list"
              onClick={() => setFocused(true)}
            >
              <CollapseIcon />
            </button>
            <button
              className="control quiet stop"
              title={`Signed in as ${me.email}`}
              onClick={() => setConfirmingSignOut(true)}
            >
              <SignOutIcon /> Sign out
            </button>
          </div>

          {openings.length > 1 ? (
            <select
              className="field"
              value={openingId ?? ""}
              onChange={(event) => {
                setOpeningId(event.target.value);
                setSelected(null);
              }}
              style={{ marginBottom: 8 }}
            >
              {openings.map((opening) => (
                <option key={opening.id} value={opening.id}>
                  {opening.title}
                </option>
              ))}
            </select>
          ) : (
            <h1 className="opening-title">{page?.opening_title ?? "Candidates"}</h1>
          )}

          <p className="tally">
            <span className="num">{page?.total ?? 0}</span> applications ·{" "}
            <span className="num">{page?.evaluated ?? 0}</span> examined
            {waiting > 0 && (
              <>
                {" · "}
                <span className="num">{waiting}</span> awaiting examination
              </>
            )}
          </p>

          <div className="filters">
            {FILTERS.map((option) => (
              <button
                key={option.id}
                className="control"
                aria-pressed={filter === option.id}
                onClick={() => setFilter(option.id)}
              >
                {option.label}
              </button>
            ))}
          </div>

          <div className="search">
            <input
              className="field"
              placeholder="Search by name or anything in a résumé…"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
            />
          </div>
        </div>

        {error && <p className="notice-error" style={{ padding: "12px 18px" }}>{error}</p>}

        {picked !== null && (
          <p className="picking-note">
            {picked.length === 0
              ? "Pick two candidates to line up. Only examined ones can be compared."
              : picked.length === 1
                ? "One picked. Pick another."
                : `${picked.length} picked · at most ${MAX_COMPARED}`}
          </p>
        )}

        {visible.map((item, index) => (
          <Exhibit
            key={item.id}
            item={item}
            rank={index + 1}
            selected={picked !== null ? picked.includes(item.id) : item.id === selected}
            picking={picked !== null}
            onSelect={picked !== null ? pick : setSelected}
          />
        ))}

        {page && visible.length === 0 && (
          <p className="empty">
            <strong>Nothing here</strong>
            {query.trim()
              ? "No application matches that search."
              : "No application matches this view."}
          </p>
        )}
      </div>

      <div className="register" ref={plate}>
        {picked !== null ? (
          comparison ? (
            <Comparison result={comparison} />
          ) : (
            <p className="empty">
              <strong>Compare two candidates</strong>
              A score answers "is this one good". The real question is "this one or that one" —
              pick two on the left and this shows exactly which criteria separate them.
            </p>
          )
        ) : detail ? (
          <Plate
            detail={detail}
            onChanged={() => {
              reload();
              reloadDetail();
            }}
          />
        ) : (
          <p className="empty">
            <strong>Choose an application</strong>
            Every score on the left is backed by sentences from the résumé itself. Open one to
            see which.
          </p>
        )}
      </div>

      {shareUrl && (
        <ShareMade url={shareUrl} onClose={() => setShareUrl(null)} />
      )}

      <Confirm
        open={confirmingSignOut}
        title="Sign out of Verbatim?"
        body="You will need your email and password to get back in. Anything you have decided is already saved."
        confirmLabel="Sign out"
        destructive
        onCancel={() => setConfirmingSignOut(false)}
        onConfirm={() => api.logout().finally(onSignedOut)}
      />
    </div>
  );
}


function ShareMade({ url, onClose }: { url: string; onClose: () => void }) {
  const [copied, setCopied] = useState(false);

  return (
    <div className="share-made" role="status">
      <p className="share-made-title">A read-only link to the shortlist</p>
      <p className="hint">
        Anyone with it can read the shortlist and the evidence, and nothing else. It expires in
        fourteen days. <strong>Copy it now</strong> — it is stored hashed and cannot be shown
        again.
      </p>
      <div className="share-made-row">
        <input className="field num" readOnly value={url} onFocus={(e) => e.target.select()} />
        <button
          className="control"
          onClick={() => {
            navigator.clipboard?.writeText(url).then(
              () => setCopied(true),
              () => setCopied(false),
            );
          }}
        >
          {copied ? "Copied" : "Copy"}
        </button>
        <button className="control quiet" onClick={onClose}>
          Done
        </button>
      </div>
    </div>
  );
}
