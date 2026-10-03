import {
  BookOpen,
  CalendarDays,
  GraduationCap,
  ListChecks,
  LogIn,
  Moon,
  RefreshCw,
  Search,
  ShieldCheck,
  Sun,
  Users,
} from "lucide-react";
import { useEffect, useRef } from "react";
import type { ReactNode } from "react";

import { useAuth } from "../../entities/user/index.ts";
import { useSettings } from "../../shared/settings/SettingsProvider.tsx";
import { LANGUAGE_OPTIONS, useI18n } from "../../shared/i18n/index.ts";
import { useSignInChallenge } from "./useSignInChallenge.ts";

/**
 * The public landing page of the hosted service (ADR-0029).
 *
 * What a visitor gets when they open the domain with no session: an
 * explanation of what the site is and does, a sign-in entry point in the
 * header, a second one after the information, and a link to the privacy
 * policy at the very bottom. It replaces the bare "Not signed in" card for
 * the first-visit case; a session that merely EXPIRED still gets the compact
 * `SignIn` gate (see App.tsx).
 *
 * Every string goes through `t()`, so the page follows the stored language
 * and, on a first visit, the browser's preference (ADR-0011). The language
 * switcher lives here because a visitor without a session can never reach
 * Settings.
 *
 * The Turnstile widget (DDoS plan §17) is rendered once, next to the lower
 * sign-in button. Both buttons share one token: while a challenge is
 * unsolved, a click scrolls the widget into view instead of starting a flow
 * the server would only reject.
 */
export function Landing() {
  const { login } = useAuth();
  const { setLanguage, setTheme } = useSettings();
  const { t, language } = useI18n();
  const { token, required, requested, pending, widgetRef } =
    useSignInChallenge();
  const challengeRef = useRef<HTMLDivElement | null>(null);
  const isDark = document.documentElement.dataset.theme === "dark";

  // The page is public and self-describing: give it its own document title.
  // AppShell's own title effect is skipped while the landing is on screen, so
  // nothing overwrites this (see App.tsx). `<html lang>` is NOT set here: the
  // settings provider declares it for every surface, so a language switch on
  // the dashboard updates the document too (ADR-0034).
  useEffect(() => {
    document.title = t("landing.documentTitle");
  }, [t]);

  const startSignIn = () => {
    if (pending) {
      // A challenge is required and unsolved. Send the visitor to the widget
      // instead of firing a login request the server would answer 403.
      challengeRef.current?.scrollIntoView({ block: "center" });
      return;
    }
    void login(token ?? undefined);
  };

  return (
    <div className="landing">
      <header className="landing-header">
        <div className="landing-brand">
          <div className="landing-brand-logo">
            <GraduationCap size={20} />
          </div>
          <div className="landing-brand-name">{t("landing.brand")}</div>
        </div>
        <div className="landing-header-actions">
          <label className="landing-language">
            <span className="landing-language-label">
              {t("landing.languageLabel")}
            </span>
            <select
              value={language}
              onChange={(event) =>
                setLanguage(event.target.value as typeof language)
              }
            >
              {LANGUAGE_OPTIONS.map((option) => (
                <option key={option.code} value={option.code}>
                  {option.label}
                </option>
              ))}
            </select>
          </label>
          <button
            type="button"
            className="icon-button"
            aria-label={t("topbar.toggleTheme")}
            onClick={() => setTheme(isDark ? "light" : "dark")}
          >
            {isDark ? <Sun size={18} /> : <Moon size={18} />}
          </button>
          <button
            type="button"
            className="button button-primary"
            onClick={startSignIn}
          >
            <LogIn size={15} />
            {t("landing.signIn")}
          </button>
        </div>
      </header>
      <main className="landing-main">
        <section className="landing-hero">
          <h1>{t("landing.heroTitle")}</h1>
          <p className="landing-lead">{t("landing.heroLead")}</p>
          <p className="landing-hint">{t("landing.signInHint")}</p>
        </section>

        <section className="landing-section">
          <h2>{t("landing.whatTitle")}</h2>
          <p className="landing-body">{t("landing.whatBody")}</p>
        </section>

        <section className="landing-section">
          <h2>{t("landing.featuresTitle")}</h2>
          <div className="landing-features">
            <Feature
              icon={<BookOpen size={20} />}
              title={t("landing.feature.subjects.title")}
              text={t("landing.feature.subjects.text")}
            />
            <Feature
              icon={<ListChecks size={20} />}
              title={t("landing.feature.assignments.title")}
              text={t("landing.feature.assignments.text")}
            />
            <Feature
              icon={<GraduationCap size={20} />}
              title={t("landing.feature.grades.title")}
              text={t("landing.feature.grades.text")}
            />
            <Feature
              icon={<CalendarDays size={20} />}
              title={t("landing.feature.calendar.title")}
              text={t("landing.feature.calendar.text")}
            />
            <Feature
              icon={<Search size={20} />}
              title={t("landing.feature.search.title")}
              text={t("landing.feature.search.text")}
            />
            <Feature
              icon={<Users size={20} />}
              title={t("landing.feature.teacher.title")}
              text={t("landing.feature.teacher.text")}
            />
          </div>
        </section>

        <section className="landing-section">
          <h2>{t("landing.howTitle")}</h2>
          <ol className="landing-steps">
            <Step
              step={1}
              title={t("landing.how.signIn.title")}
              text={t("landing.how.signIn.text")}
            />
            <Step
              step={2}
              title={t("landing.how.sync.title")}
              text={t("landing.how.sync.text")}
            />
            <Step
              step={3}
              title={t("landing.how.dashboard.title")}
              text={t("landing.how.dashboard.text")}
            />
          </ol>
        </section>
        <section className="landing-section">
          <h2>{t("landing.dataTitle")}</h2>
          <ul className="landing-data">
            <DataPoint icon={<ShieldCheck size={18} />}>
              {t("landing.data.readOnly")}
            </DataPoint>
            <DataPoint icon={<ShieldCheck size={18} />}>
              {t("landing.data.neverWrites")}
            </DataPoint>
            <DataPoint icon={<RefreshCw size={18} />}>
              {t("landing.data.storage")}
            </DataPoint>
          </ul>
          <a
            className="button landing-privacy-link"
            href="/privacy/"
            target="_blank"
            rel="noreferrer"
          >
            {t("landing.data.privacyLink")}
          </a>
        </section>

        {/*
          NO donation section here (п.9).

          ADR-0037 chose TWO entry points for `DonateCards` — this public
          section and the collapsible card in Settings — and the test in
          `Landing.test.tsx` pinned the anonymous visitor as its audience. That is
          deliberately reversed: an unsent-in visitor arrives with no account, has
          never seen the product work, and meets a page whose whole job is to
          explain what the site is and get them through Google sign-in. A
          payment QR pair in the middle of that flow interrupts the one action the
          page exists to offer, and it asks for money from someone who cannot yet
          judge whether the thing is worth supporting.

          Support is therefore asked of people who already use the product, in
          `/settings`, where it is COLLAPSED by default and nobody's sign-in
          flow is interrupted (`Settings.tsx`). The component, the `donate.*`
          dictionary keys, the CSS and the artwork are all unchanged — this is
          the removal of one entry point, not of the feature. See ADR-0038.
        */}

        <section className="landing-cta">
          <h2>{t("landing.ctaTitle")}</h2>
          <p className="landing-body">{t("landing.ctaText")}</p>
          {required ? (
            <div className="landing-challenge" ref={challengeRef}>
              <div ref={widgetRef} />
              {pending ? (
                <p className="landing-hint">
                  {requested
                    ? t("signin.turnstileRequired")
                    : t("landing.challengeHint")}
                </p>
              ) : null}
            </div>
          ) : null}
          <button
            type="button"
            className="button button-primary"
            onClick={startSignIn}
          >
            <LogIn size={15} />
            {t("landing.signIn")}
          </button>
        </section>
      </main>

      <footer className="landing-footer">
        <div className="landing-footer-links">
          <a href="/privacy/" target="_blank" rel="noreferrer">
            {t("landing.footer.privacy")}
          </a>
          <a href="/terms/" target="_blank" rel="noreferrer">
            {t("landing.footer.terms")}
          </a>
        </div>
        <div className="landing-footer-note">{t("landing.footer.notGoogle")}</div>
        <div className="landing-footer-contact">
          <span>{t("landing.footer.contact")}</span>{" "}
          <a
            href="https://github.com/MonkStone1/google_class_help"
            target="_blank"
            rel="noreferrer"
          >
            {t("landing.footer.repository")}
          </a>
        </div>
      </footer>
    </div>
  );
}

function Feature({
  icon,
  title,
  text,
}: {
  icon: ReactNode;
  title: string;
  text: string;
}) {
  return (
    <article className="landing-feature">
      <div className="landing-feature-icon">{icon}</div>
      <h3>{title}</h3>
      <p>{text}</p>
    </article>
  );
}

function Step({
  step,
  title,
  text,
}: {
  step: number;
  title: string;
  text: string;
}) {
  return (
    <li className="landing-step">
      <span className="landing-step-number">{step}</span>
      <div>
        <h3>{title}</h3>
        <p>{text}</p>
      </div>
    </li>
  );
}

function DataPoint({
  icon,
  children,
}: {
  icon: ReactNode;
  children: string;
}) {
  return (
    <li className="landing-data-point">
      <span className="landing-data-icon">{icon}</span>
      <span>{children}</span>
    </li>
  );
}
