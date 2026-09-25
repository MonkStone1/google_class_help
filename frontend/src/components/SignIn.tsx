import { GraduationCap } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { api } from "../api.ts";
import type { TurnstileConfig } from "../api.ts";
import { useAuth } from "../context/DataContext.tsx";
import { useI18n } from "../i18n.ts";

/**
 * Minimal typing of the Turnstile widget API actually used here.
 * The script is loaded from Cloudflare only when the server reports a
 * challenge (DDoS plan §17); the CSP allows that origin for scripts/frames.
 */
type TurnstileWindow = {
  turnstile?: {
    render: (
      container: HTMLElement,
      options: Record<string, unknown>,
    ) => string;
  };
};

/**
 * The login state of the hosted service (migration stage 7, §26).
 *
 * Rendered instead of the dashboard once a request answered 401: this
 * browser holds no application session, so every cached view is dropped and
 * the only way forward is signing in. Sign-in is a full-page navigation into
 * the server-owned OAuth flow (`DataContext.login` redirects when the server
 * answers 405) — the SPA never touches a Google token.
 *
 * Turnstile (DDoS plan §17, stage 10): when the server reports
 * `enabled: true`, the card renders the widget and only a SOLVED token
 * allows `login(token)` to hit `POST /api/auth/login/start`. The secret key
 * stays on the backend; the browser sees only the public site key.
 *
 * The desktop build never reaches this gate: its `/api/auth/status` always
 * answers 200 and reports `authenticated: false` until the loopback consent
 * completes, so the desktop workflow keeps its hints in place.
 */
export function SignIn() {
  const { login } = useAuth();
  const { t } = useI18n();
  const widgetRef = useRef<HTMLDivElement | null>(null);
  const [turnstile, setTurnstile] = useState<TurnstileConfig | null>(null);
  const [token, setToken] = useState<string | null>(null);
  const challengeRequired =
    new URLSearchParams(window.location.search).get("challenge") ===
    "required";

  // One lightweight public config call; failure = no challenge (default).
  useEffect(() => {
    let cancelled = false;
    api
      .getTurnstileConfig()
      .then((config) => {
        if (!cancelled) setTurnstile(config);
      })
      .catch(() => {
        if (!cancelled) setTurnstile({ enabled: false, site_key: null });
      });
    return () => {
      cancelled = true;
    };
  }, []);

  // Load the widget script once and render it into the card when configured.
  useEffect(() => {
    const siteKey = turnstile?.enabled ? turnstile.site_key : null;
    if (!siteKey) return;
    const container = widgetRef.current;
    if (!container) return;
    let cancelled = false;
    const render = () => {
      if (cancelled) return;
      const w = window as unknown as TurnstileWindow;
      w.turnstile?.render(container, {
        sitekey: siteKey,
        callback: (value: string) => setToken(value),
        "expired-callback": () => setToken(null),
        "error-callback": () => setToken(null),
      });
    };
    const scriptId = "gch-turnstile-script";
    if (document.getElementById(scriptId)) {
      render();
      return () => {
        cancelled = true;
      };
    }
    const script = document.createElement("script");
    script.id = scriptId;
    script.src =
      "https://challenges.cloudflare.com/turnstile/v0/api.js?render=explicit";
    script.async = true;
    script.onload = render;
    document.head.appendChild(script);
    return () => {
      cancelled = true;
    };
  }, [turnstile]);

  const needsChallenge = Boolean(turnstile?.enabled);
  const canSubmit = !needsChallenge || Boolean(token);

  return (
    <div className="signin-gate">
      <section className="card signin-card">
        <div className="signin-icon">
          <GraduationCap size={30} />
        </div>
        <h1>{t("subjects.notSignedIn")}</h1>
        <p>{t("subjects.notSignedInHint")}</p>
        {challengeRequired && needsChallenge ? (
          <p>{t("signin.turnstileRequired")}</p>
        ) : null}
        {needsChallenge ? (
          <div>
            <div ref={widgetRef} />
            {token === null ? (
              <p>{t("signin.turnstilePending")}</p>
            ) : null}
          </div>
        ) : null}
        <button
          type="button"
          className="button button-primary"
          onClick={() => void login(token ?? undefined)}
          disabled={!canSubmit}
        >
          {t("settings.signIn")}
        </button>
      </section>
    </div>
  );
}
