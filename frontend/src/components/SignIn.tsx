import { GraduationCap } from "lucide-react";

import { useAuth } from "../context/DataContext.tsx";
import { useI18n } from "../i18n.ts";

/**
 * The login state of the hosted service (migration stage 7, §26).
 *
 * Rendered instead of the dashboard once a request answered 401: this
 * browser holds no application session, so every cached view is dropped and
 * the only way forward is signing in. Sign-in is a full-page navigation into
 * the server-owned OAuth flow (`DataContext.login` redirects when the server
 * answers 405) — the SPA never touches a Google token.
 *
 * The desktop build never reaches this gate: its `/api/auth/status` always
 * answers 200 and reports `authenticated: false` until the loopback consent
 * completes, so the desktop workflow keeps its hints in place.
 */
export function SignIn() {
  const { login } = useAuth();
  const { t } = useI18n();

  return (
    <div className="signin-gate">
      <section className="card signin-card">
        <div className="signin-icon">
          <GraduationCap size={30} />
        </div>
        <h1>{t("subjects.notSignedIn")}</h1>
        <p>{t("subjects.notSignedInHint")}</p>
        <button
          type="button"
          className="button button-primary"
          onClick={() => void login()}
        >
          {t("settings.signIn")}
        </button>
      </section>
    </div>
  );
}
