import { useEffect, useState } from "react";
import { Apply, Received } from "./apply/Apply";
import type { User } from "./lib/api";
import { PasswordField } from "./components/PasswordField";
import { RateLimited, api } from "./lib/api";
import { navigate, useRoute } from "./lib/router";
import { Shared } from "./shared/Shared";
import { Home } from "./site/Home";
import { Panel } from "./panel/Panel";

export default function App() {
  const route = useRoute();
  const [me, setMe] = useState<User | null>(null);
  const [checking, setChecking] = useState(true);

  // Only the panel asks who is here. The site and the application pages are public.
  const isPublic = route.name !== "panel";

  useEffect(() => {
    if (isPublic) {
      setChecking(false);
      return;
    }
    // Ask the server rather than trusting anything local: the session may have
    // been revoked since this tab was opened.
    api
      .me()
      .then(setMe)
      .catch(() => setMe(null))
      .finally(() => setChecking(false));
  }, [isPublic]);

  if (route.name === "home") return <Home />;
  if (route.name === "apply") return <Apply slug={route.slug} />;
  if (route.name === "applied") return <Received reference={route.reference} />;
  if (route.name === "shared") return <Shared token={route.token} />;
  if (route.name === "missing") return <NotFound />;
  if (checking) return <p className="empty">Loading…</p>;
  if (!me) return <SignIn onDone={setMe} />;
  return <Panel me={me} onSignedOut={() => setMe(null)} />;
}

function SignIn({ onDone }: { onDone: (user: User) => void }) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      onDone(await api.login(email.trim(), password));
    } catch (caught) {
      // One message for every credential failure, whatever went wrong. Saying
      // "no such account" would turn this form into a way to find out who has
      // one. The lockout is the single exception: telling someone their password
      // is wrong while the account is throttled would have them retry for
      // fifteen minutes, and it reveals nothing about whether the account exists.
      setError(
        caught instanceof RateLimited
          ? "Too many attempts. Try again in a few minutes."
          : "Email or password incorrect.",
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="gate">
      <form onSubmit={submit}>
        <h1 className="wordmark">Verbatim</h1>
        <p className="lede">
          Every score comes with the sentence it came from. Sign in to review candidates.
        </p>
        <label className="stack">
          <span>Email</span>
          <input
            className="field"
            type="email"
            autoComplete="username"
            value={email}
            onChange={(event) => setEmail(event.target.value)}
          />
        </label>
        <label className="stack">
          <span>Password</span>
          <PasswordField value={password} onChange={setPassword} />
        </label>
        <button className="control primary" type="submit" disabled={busy || !email || !password}>
          {busy ? "Signing in…" : "Sign in"}
        </button>
        {error && <p className="notice-error">{error}</p>}
        <p className="hint" style={{ marginTop: 18 }}>
          <a href="/">Back to verbatim</a>
        </p>
      </form>
    </div>
  );
}


function NotFound() {
  return (
    <div className="gate">
      <div style={{ maxWidth: 380 }}>
        <h1 className="wordmark">Nothing here</h1>
        <p className="lede">
          That address does not lead anywhere. If you were sent a link to apply for a job, check
          it was copied in full.
        </p>
        <button className="control" onClick={() => navigate("/")}>
          Go to the start
        </button>
      </div>
    </div>
  );
}
