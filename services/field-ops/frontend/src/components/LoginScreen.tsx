/**
 * LoginScreen — the only way into the app.
 *
 * `login()` has existed in services/api.ts since the service was scaffolded,
 * but nothing ever called it and there was no form: the PWA could not
 * authenticate itself. The only way to use it was to mint a JWT by hand and
 * write it into localStorage, which is not something a field observer can do
 * on a phone at a monument.
 *
 * Session length is deliberately long (8 h, set server-side) so a full day's
 * shift does not require re-authenticating in the field, where re-entering a
 * password one-handed in sunlight is its own hazard.
 */

import { useState } from "react";
import { login } from "../services/api";

interface Props {
  onSuccess: () => void;
}

export default function LoginScreen({ onSuccess }: Props) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const onSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      await login(username.trim(), password);
      onSuccess();
    } catch (err) {
      // Offline is the likely cause in the field, and it needs a different
      // answer from "wrong password" — one is retryable where you stand, the
      // other is not.
      setError(
        !navigator.onLine
          ? "No connection. You must log in once while online; after that the app works offline for the rest of the session."
          : err instanceof Error
            ? err.message
            : "Sign in failed"
      );
    } finally {
      setBusy(false);
    }
  };

  return (
    <form className="login-form" onSubmit={onSubmit}>
      <h2>Sign in</h2>
      <p className="hint">
        Use the account issued for this fieldwork. Your session stays active for
        the working day.
      </p>

      <label>
        Username
        <input
          type="text"
          value={username}
          onChange={(e) => setUsername(e.target.value)}
          autoComplete="username"
          autoCapitalize="none"
          autoCorrect="off"
          spellCheck={false}
          required
          disabled={busy}
        />
      </label>

      <label>
        Password
        <input
          type="password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          autoComplete="current-password"
          required
          disabled={busy}
        />
      </label>

      {error && <p className="msg msg-error">{error}</p>}

      <button type="submit" className="submit-btn" disabled={busy || !username || !password}>
        {busy ? "Signing in…" : "Sign in"}
      </button>
    </form>
  );
}
