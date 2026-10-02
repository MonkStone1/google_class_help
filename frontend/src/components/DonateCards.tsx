import { useEffect, useRef, useState } from "react";
import { X } from "lucide-react";

import { useI18n } from "../i18n.ts";
import type { I18nKey } from "../i18n.ts";

/**
 * The two donation destinations, in display order.
 *
 * The artwork lives in `frontend/public/donate/`, not in `src/assets/`: Vite
 * copies `public/` verbatim into `dist`, and `dist` is what actually ships —
 * the Docker image (Dockerfile, stage `frontend-build`) and the one-file
 * desktop exe (`build.bat --include-data-dir=frontend/dist`). `public/` is
 * where this project keeps unprocessed binaries that must reach the bundle
 * unchanged, the same rule the favicons follow (ADR-0031).
 *
 * `width`/`height` are the REAL pixel size of each file. The two are NOT
 * square (1051×1280 and 1056×1280) and not even equal to each other, so they
 * are carried per bank: the browser then reserves the correct box before the
 * image loads, and the CSS keeps `height: auto` so a later replacement of a
 * different shape is never squashed. A hard-coded square here is exactly what
 * would silently stretch a code past the point where a bank app reads it.
 *
 * `nameKey` keeps the bank name in the dictionaries, where it is needed for
 * the `alt` text and the preview caption. The name is painted INTO the
 * artwork, so a visible label under the card would only repeat it.
 */
const BANKS: ReadonlyArray<{
  id: string;
  file: string;
  nameKey: I18nKey;
  width: number;
  height: number;
}> = [
  {
    id: "monobank",
    file: "monobank.png",
    nameKey: "donate.bank.monobank",
    width: 1051,
    height: 1280,
  },
  {
    id: "privatbank",
    file: "privatbank.png",
    nameKey: "donate.bank.privatbank",
    width: 1056,
    height: 1280,
  },
];

/**
 * The donation block: where the money goes, and the two QR codes (ADR-0037).
 *
 * ONE component, TWO entry points — the public landing section and the
 * collapsible Settings card render exactly this markup, so the wording, the
 * order of the banks and the accessibility of the images cannot drift apart
 * between an anonymous visitor and a signed-in user.
 *
 * Two deliberate choices:
 *
 * - **The artwork is shown as delivered.** No white plate, no tint, no
 *   `filter`: each PNG already carries the bank's own background, the QR and
 *   the account name, so recolouring it would stop the code from scanning.
 *   The card around it is what adapts to the theme instead.
 * - **Each code is a BUTTON, not a bare image.** At the size that fits two of
 *   them on a page a phone camera cannot read the code at arm's length, so a
 *   click opens the full-size file. The button is what makes that reachable
 *   by keyboard and announced by a screen reader — the image alone would be
 *   inert, and the enlarged view is the whole point of the feature.
 */
export function DonateCards() {
  const { t } = useI18n();
  const [preview, setPreview] = useState<(typeof BANKS)[number] | null>(null);
  // Where focus has to return when the preview closes, so dismissing it with
  // the keyboard does not drop the reader back at the top of the document.
  const triggerRef = useRef<HTMLButtonElement | null>(null);

  // Escape closes the preview. The listener exists only while it is open, so
  // the page never carries more than this one extra key handler.
  useEffect(() => {
    if (!preview) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setPreview(null);
        triggerRef.current?.focus();
      }
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [preview]);

  const closePreview = () => {
    setPreview(null);
    triggerRef.current?.focus();
  };

  return (
    <div className="donate">
      <p className="donate-note">{t("donate.note")}</p>
      <ul className="donate-grid">
        {BANKS.map((bank) => {
          const name = t(bank.nameKey);
          return (
            <li key={bank.id} className="donate-card">
              <button
                type="button"
                className="donate-open"
                aria-label={t("donate.preview", { bank: name })}
                onClick={(event) => {
                  triggerRef.current = event.currentTarget;
                  setPreview(bank);
                }}
              >
                {/* Empty `alt` on purpose: the surrounding BUTTON already
                    carries the bank's name in its `aria-label`, and that label
                    wins as the button's accessible name. Leaving a second copy
                    of the same text in the image would have a screen reader
                    announce the bank twice. The enlarged copy below keeps a
                    real `alt` because there it is the only description. */}
                <img
                  className="donate-qr"
                  src={`/donate/${bank.file}`}
                  alt=""
                  width={bank.width}
                  height={bank.height}
                  loading="lazy"
                />
              </button>
            </li>
          );
        })}
      </ul>

      {/*
        The enlarged view. It reuses `.modal-backdrop` — the same overlay the
        assignment and confirmation dialogs already ship (ADR-0035), so the
        dismissal behaviour is the one the app already has: Escape, a click on
        the backdrop, or the close button.
      */}
      {preview ? (
        <div
          className="modal-backdrop donate-preview-backdrop"
          role="presentation"
          onClick={closePreview}
        >
          <div
            className="donate-preview"
            role="dialog"
            aria-modal="true"
            aria-label={t("donate.preview", { bank: t(preview.nameKey) })}
            onClick={(event) => event.stopPropagation()}
          >
            <div className="donate-preview-header">
              <span className="donate-preview-title">
                {t(preview.nameKey)}
              </span>
              <button
                type="button"
                className="icon-button"
                onClick={closePreview}
                aria-label={t("modal.close")}
              >
                <X size={18} />
              </button>
            </div>
            {/* The full-size file, so a phone has room to scan it. Bounded to
                the viewport rather than shown at its natural 1280px height. */}
            <img
              className="donate-preview-image"
              src={`/donate/${preview.file}`}
              alt={t("donate.qrAlt", { bank: t(preview.nameKey) })}
              width={preview.width}
              height={preview.height}
            />
          </div>
        </div>
      ) : null}
    </div>
  );
}
