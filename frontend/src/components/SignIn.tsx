import { GraduationCap } from "lucide-react";

import { useAuth } from "../context/DataContext.tsx";
import { useI18n } from "../i18n.ts";
import { useSignInChallenge } from "../lib/signInChallenge.ts";

/**
 * The compact login gate of the hosted service (migration stage 7, §26).
 *
 * Shown when a session that DID exist is gone — the signed-in browser hit a
 * 401 mid-use. A visitor who never had a session gets the public `Landing`
 * page instead (ADR-0029), which is the better surface for "what is this
 * site"; here the user only needs the way back in.
 *
 * Sign-in is a full-page navigation into the server-owned OAuth flow
 * (`DataContext.login` redirects when the server answers 405) — the SPA never
 * touches a Google token.
 *
 * The desktop build never reaches this gate: its `/api/auth/status` always
 * answers 200 and reports `authenticated: false` until the loopback consent
 * completes, so the desktop workflow keeps its hints in place.
 */
export function SignIn() {
  const { login } = useAuth();
  const { t } = useI18n();
  const { token, required, requested, widgetRef } = useSignInChallenge();
  const canSubmit = !required || Boolean(token);

  return (
    <div className="signin-gate">
      <section className="card signin-card">
        <div className="signin-icon">
          <GraduationCap size={30} />
        </div>
        <h1>{t("subjects.notSignedIn")}</h1>
        <p>{t("subjects.notSignedInHint")}</p>
        {requested && required ? (
          <p>{t("signin.turnstileRequired")}</p>
        ) : null}
        {required ? (
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

