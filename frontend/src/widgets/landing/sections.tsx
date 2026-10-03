/**
 * The three presentational blocks of the landing page.
 *
 * Each is markup with a class name and three strings — no state, no data, no
 * decision. They live apart from `Landing.tsx` because a section of the page is
 * the thing that changes when the copy changes, and burying it under a page
 * that also owns the sign-in flow made both harder to read than either.
 */

import type { ReactNode } from "react";

/** One promise of the product: an icon, a title and one sentence. */
export function Feature({
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

/** One step of the "how it works" list, numbered. */
export function Step({
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

/** One bullet of "what data we touch", with its icon. */
export function DataPoint({
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