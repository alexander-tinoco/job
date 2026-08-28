import { useEffect, useRef, useState } from "react";
import { Confirm } from "../components/Confirm";
import { navigate } from "../lib/router";

interface PublicOpening {
  slug: string;
  title: string;
  description: string;
  company_name: string;
  status: "open" | "closed";
  closes_at: string | null;
}

const MAX_BYTES = 10 * 1024 * 1024;

export function Apply({ slug }: { slug: string }) {
  const [opening, setOpening] = useState<PublicOpening | null>(null);
  const [missing, setMissing] = useState(false);

  useEffect(() => {
    fetch(`/openings/${encodeURIComponent(slug)}`)
      .then((response) => (response.ok ? response.json() : Promise.reject()))
      .then(setOpening)
      .catch(() => setMissing(true));
  }, [slug]);

  if (missing) {
    return (
      <div className="apply">
        <div className="receipt">
          <h1>This opening is not available</h1>
          <p>The link may have expired, or the role may have been filled.</p>
        </div>
      </div>
    );
  }
  if (!opening) return <div className="empty">Loading…</div>;

  // The browser tab belongs to the company too, not to us.
  document.title = `${opening.title} · ${opening.company_name}`;

  return (
    <div className="apply">
      {/* The hiring company's page, not ours. Their name leads. */}
      <header className="apply-band">
        <div className="inner">
          <p className="apply-company">{opening.company_name}</p>
          <h1 className="apply-role">{opening.title}</h1>
          {opening.closes_at && (
            <p className="apply-meta">
              Applications close{" "}
              {new Date(opening.closes_at).toLocaleDateString(undefined, {
                day: "numeric",
                month: "long",
              })}
            </p>
          )}
        </div>
      </header>

      <div className="apply-body">
        {opening.description && <Description text={opening.description} />}
        {opening.status === "closed" ? (
          <>
            <h2>Applications are closed</h2>
            <p className="hint">
              This opening is no longer accepting applications. Thank you for your interest.
            </p>
          </>
        ) : (
          <ApplicationForm opening={opening} />
        )}
        <p className="signature">
          Applications are received through Verbatim on behalf of {opening.company_name}.
        </p>
      </div>
    </div>
  );
}

function ApplicationForm({ opening }: { opening: PublicOpening }) {
  const [file, setFile] = useState<File | null>(null);
  const [consent, setConsent] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [sending, setSending] = useState(false);
  const [armed, setArmed] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const input = useRef<HTMLInputElement>(null);
  const form = useRef<HTMLFormElement>(null);

  function choose(candidate: File | undefined) {
    if (!candidate) return;
    if (candidate.size > MAX_BYTES) {
      setError("That file is larger than 10 MB. Please upload a smaller PDF.");
      return;
    }
    setError(null);
    setFile(candidate);
  }

  function review(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!file) {
      setError("Please attach your résumé as a PDF.");
      return;
    }
    setError(null);
    // An application cannot be unsent, and a candidate gets one.
    setConfirming(true);
  }

  async function send() {
    if (!file || !form.current) return;
    setSending(true);
    setError(null);

    const body = new FormData(form.current);
    body.set("consent", "true");
    body.set("resume", file);

    try {
      const response = await fetch(`/openings/${encodeURIComponent(opening.slug)}/apply`, {
        method: "POST",
        body,
      });
      if (!response.ok) {
        const body = (await response.json().catch(() => null)) as { detail?: unknown } | null;
        const detail = body?.detail;
        // The API answers a validation failure with a list; a rule with a string.
        throw new Error(
          typeof detail === "string"
            ? detail
            : "We could not accept that application. Please check your details and try again.",
        );
      }
      const receipt = (await response.json()) as { application_id: string };
      navigate(`/apply/${opening.slug}/received/${receipt.application_id}`);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : String(caught));
      setSending(false);
      setConfirming(false);
    }
  }

  return (
    <form ref={form} onSubmit={review} noValidate>
      <h2>Apply</h2>

      <label className="stack">
        <span>Full name</span>
        <input className="field" name="full_name" required autoComplete="name" />
      </label>

      <label className="stack">
        <span>Email</span>
        <input className="field" name="email" type="email" required autoComplete="email" />
      </label>

      <label className="stack">
        <span>Phone — optional</span>
        <input className="field" name="phone" autoComplete="tel" />
      </label>

      <label className="stack">
        <span>LinkedIn — optional</span>
        <input className="field" name="linkedin_url" inputMode="url" />
      </label>

      <label className="stack">
        <span>Résumé</span>
        <div
          className="dropzone"
          data-armed={armed}
          onDragOver={(event) => {
            event.preventDefault();
            setArmed(true);
          }}
          onDragLeave={() => setArmed(false)}
          onDrop={(event) => {
            event.preventDefault();
            setArmed(false);
            choose(event.dataTransfer.files[0]);
          }}
        >
          <input
            ref={input}
            type="file"
            accept="application/pdf,.pdf"
            hidden
            onChange={(event) => choose(event.target.files?.[0])}
          />
          {file ? (
            <>
              <p className="filename">{file.name}</p>
              <button
                type="button"
                className="control quiet"
                onClick={() => setFile(null)}
                style={{ marginTop: 6 }}
              >
                Choose a different file
              </button>
            </>
          ) : (
            <>
              <button
                type="button"
                className="control"
                onClick={() => input.current?.click()}
              >
                Choose a PDF
              </button>
              <p className="hint">or drop it here · PDF only, up to 10 MB</p>
            </>
          )}
        </div>
      </label>

      <label className="consent">
        <input
          type="checkbox"
          checked={consent}
          onChange={(event) => setConsent(event.target.checked)}
        />
        <span>
          I agree that {opening.company_name} may store and review my résumé for this
          application. It is deleted six months after the opening closes, and I can ask for it
          to be removed sooner.
        </span>
      </label>

      <button className="control primary" type="submit" disabled={!consent || sending}>
        Send application
      </button>
      {error && <p className="notice-error">{error}</p>}

      <Confirm
        open={confirming}
        title="Send your application?"
        body={`Your details and résumé go to ${opening.company_name}. You can apply to this opening only once, so check your file is the right one before sending.`}
        confirmLabel="Send it"
        busy={sending}
        onCancel={() => !sending && setConfirming(false)}
        onConfirm={send}
      />
    </form>
  );
}

function Description({ text }: { text: string }) {
  return (
    <p className="description">
      {text.split("\n").map((line, index) =>
        /^[A-Z][A-Z ,&]{3,}$/.test(line.trim()) ? (
          <b key={index}>{line.trim()}</b>
        ) : (
          // The newline must be inside the braces: bare "\n" in JSX text is two
          // literal characters, and white-space: pre-wrap then prints them.
          <span key={index}>{`${line}\n`}</span>
        ),
      )}
    </p>
  );
}

export function Received({ reference }: { reference: string }) {
  useEffect(() => {
    document.title = "Application sent";
  }, []);

  return (
    <div className="apply">
      <div className="sent">
        <svg
          className="tick"
          viewBox="0 0 40 40"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.6"
          strokeLinecap="round"
          strokeLinejoin="round"
          aria-hidden
        >
          <circle cx="20" cy="20" r="17" />
          <path d="M12.5 20.5 17.8 26 27.5 14.5" />
        </svg>
        <h1>Your application is in</h1>
        <p>
          A person will read it. Every application to this opening is read; none is filtered out
          automatically.
        </p>
        <p>
          If your experience fits the role, the hiring team will contact you by email. You do not
          need to do anything else.
        </p>
        <p className="reference">Reference {reference.slice(0, 8)}</p>
        <p className="close-hint">You can close this tab.</p>
      </div>
    </div>
  );
}
