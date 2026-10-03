import { AlertTriangle, CheckCircle2, Info, KeyRound } from "lucide-react";
import { Toaster as SonnerToaster } from "sonner";

import { useSettings } from "../shared/settings/SettingsProvider.tsx";
import { useI18n } from "../shared/i18n/index.ts";

/**
 * The toast host (ADR-0030).
 *
 * Sonner owns the animation, the stack and the swipe-to-dismiss; everything it
 * paints is repainted in the app's own tokens by the `Sonner toasts` block in
 * `styles/components.css`, so there is no second palette to keep in sync and
 * the dark theme follows `data-theme` for free.
 *
 * Two things are deliberately NOT done:
 * - `sonner/dist/styles.css` is never imported. Sonner injects its stylesheet
 *   from the module body, and importing the file as well would duplicate every
 *   rule. The injection also lands in `<head>` *after* our bundle, which is why
 *   the token overrides in `components.css` raise the specificity instead of
 *   relying on load order.
 * - the default `alt+T` hotkey is left alone; it only repeats the newest toast
 *   and the app advertises no other shortcut.
 *
 * The two placement values are tied to the layout, not picked by eye:
 * - **Top-right, not bottom-left.** The bottom-left corner of the window is
 *   the sidebar on every page of the app: the "N overdue" block (`.sidebar-
 *   alert`, `margin-top: auto`) is pinned to its bottom next to the last nav
 *   items, and a 356px-wide toast covered their text outright.
 * - **`top` is `var(--toast-top)`, not 16px.** The region is `position: fixed`,
 *   so a small offset would lay the toast over the topbar itself — over the
 *   Sync button, the bell and the theme toggle, blocking their clicks. The
 *   token equals the topbar height plus a gap and is overridden on narrow
 *   screens, where the topbar wraps onto two rows (base.css / pages.css).
 * - `left` sits next to `right` in `mobileOffset` on purpose: on ≤600px sonner
 *   sizes the toast as `calc(100% - var(--mobile-offset-left) * 2)`, and
 *   without `left` that resolves to `auto` and the toast runs off-screen.
 */
export function Toaster() {
  const { resolvedTheme } = useSettings();
  const { t } = useI18n();

  return (
    <SonnerToaster
      position="top-right"
      theme={resolvedTheme}
      richColors
      closeButton
      duration={5000}
      visibleToasts={3}
      offset={{ right: 24, top: "var(--toast-top)" }}
      mobileOffset={{ left: 16, right: 16, top: "var(--toast-top)" }}
      containerAriaLabel={t("toast.region")}
      toastOptions={{ closeButtonAriaLabel: t("toast.dismiss") }}
      icons={{
        success: <CheckCircle2 size={18} />,
        error: <AlertTriangle size={18} />,
        warning: <KeyRound size={18} />,
        info: <Info size={18} />,
      }}
    />
  );
}
