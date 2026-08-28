import { useEffect, useState } from "react";
import { Apply, Received } from "./apply/Apply";
import type { User } from "./lib/api";
import { api } from "./lib/api";
import { useRoute } from "./lib/router";
import { Panel } from "./panel/Panel";

export default function App() {
  const route = useRoute();
  const [me, setMe] = useState<User | null>(null);
  const [checking, setChecking] = useState(true);

  // The applicant's surfaces are public; only the panel asks who is here.
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

  if (route.name === "apply") return <Apply slug={route.slug} />;
  if (route.name === "applied") return <Received reference={route.reference} />;
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
      // Whatever the server said — and it answers the same for an unknown email
      // as for a wrong password.
      setError(caught instanceof Error ? caught.message : String(caught));
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
          <input
            className="field"
            type="password"
            autoComplete="current-password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
          />
        </label>
        <button className="control primary" type="submit" disabled={busy || !email || !password}>
          {busy ? "Signing in…" : "Sign in"}
        </button>
        {error && <p className="notice-error">{error}</p>}
      </form>
    </div>
  );
}
