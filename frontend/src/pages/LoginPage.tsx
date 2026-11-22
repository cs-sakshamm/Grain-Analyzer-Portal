import { ShieldCheck } from "lucide-react";
import { useState, type FormEvent } from "react";
import { useLocation, useNavigate } from "react-router-dom";

import { useAuth } from "@/features/auth/auth-context";
import { errorMessage } from "@/services/apiClient";

type LocationState = { from?: string } | null;

export function LoginPage() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);

    if (!/^\S+@\S+\.\S+$/.test(email.trim())) {
      setError("Enter a valid email address.");
      return;
    }
    if (!password) {
      setError("Enter your password.");
      return;
    }

    setSubmitting(true);
    try {
      await login(email.trim(), password);
      const state = location.state as LocationState;
      navigate(state?.from && state.from !== "/login" ? state.from : "/", { replace: true });
    } catch (loginError) {
      setError(errorMessage(loginError));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-app px-6 py-12">
      <div className="w-full max-w-md">
        <div className="mb-6 flex items-center gap-3">
          <ShieldCheck aria-hidden="true" className="size-6 text-brand" />
          <div>
            <p className="text-sm font-semibold tracking-wide text-text">RICE AGE</p>
            <p className="text-xs text-text-muted">Departmental quality portal</p>
          </div>
        </div>

        <div className="rounded-xl border border-border-subtle bg-surface p-8 shadow-card">
          <h1 className="text-xl font-semibold text-text">Sign in</h1>
          <p className="mt-1 text-sm text-text-muted">
            Use the account issued by your department administrator.
          </p>

          <form className="mt-6 space-y-4" onSubmit={handleSubmit} noValidate>
            <div>
              <label htmlFor="email" className="block text-sm font-medium text-text">
                Email
              </label>
              <input
                id="email"
                name="email"
                type="email"
                autoComplete="username"
                required
                value={email}
                onChange={(event) => setEmail(event.target.value)}
                className="mt-1 w-full rounded-md border border-border-subtle bg-app px-3 py-2 text-sm text-text outline-none focus:border-brand"
              />
            </div>

            <div>
              <label htmlFor="password" className="block text-sm font-medium text-text">
                Password
              </label>
              <input
                id="password"
                name="password"
                type="password"
                autoComplete="current-password"
                required
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                className="mt-1 w-full rounded-md border border-border-subtle bg-app px-3 py-2 text-sm text-text outline-none focus:border-brand"
              />
            </div>

            {error ? (
              <p role="alert" className="rounded-md border border-status-flag/30 bg-status-flag/10 px-3 py-2 text-sm text-status-flag">
                {error}
              </p>
            ) : null}

            <button
              type="submit"
              disabled={submitting}
              className="w-full rounded-md bg-brand px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-brand-strong disabled:cursor-not-allowed disabled:opacity-60"
            >
              {submitting ? "Signing in…" : "Sign in"}
            </button>
          </form>
        </div>

        <p className="mt-6 text-xs leading-relaxed text-text-muted">
          Advisory prototype. Access is limited to authorized departmental users. No
          self-registration is available; contact an administrator for an account.
        </p>
      </div>
    </div>
  );
}
