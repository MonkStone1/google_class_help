import { ChevronDown } from "lucide-react";
import { useId, useState } from "react";
import type { ReactNode } from "react";

type Props = {
  /** Card heading; also the accessible name of the toggle that opens it. */
  title: string;
  children: ReactNode;
  /**
   * Whether the card starts expanded. Defaults to COLLAPSED: a block nobody
   * asked to see (donation codes, ADR-0037) must not push the settings a user
   * came for down the page, and it must not sit expanded on every visit.
   */
  defaultOpen?: boolean;
};

/**
 * A `card` whose body can be folded away behind its own heading.
 *
 * A real button with `aria-expanded`/`aria-controls`, not `<details>`: the
 * heading has to be a full-width row with a chevron on the right, and
 * `<summary>` cannot hold that markup without leaking the marker
 * (`student-grade-links summary` in `pages.css` is the only `<details>` in the
 * codebase, and it is a link list, not a card).
 *
 * The chevron rotates through CSS on `[aria-expanded="true"]`, so the open
 * state is visible without a second icon and without any state leaking into
 * the markup beyond the attribute the tests already read.
 */
export function CollapsibleCard({ title, children, defaultOpen = false }: Props) {
  const [open, setOpen] = useState(defaultOpen);
  const bodyId = useId();

  return (
    <section className="card settings-card collapsible-card">
      <button
        type="button"
        className="collapsible-card-header"
        aria-expanded={open}
        aria-controls={bodyId}
        onClick={() => setOpen((value) => !value)}
      >
        <span className="collapsible-card-title">{title}</span>
        <ChevronDown size={17} className="collapsible-card-chevron" />
      </button>
      {open ? (
        <div id={bodyId} className="collapsible-card-body">
          {children}
        </div>
      ) : null}
    </section>
  );
}
