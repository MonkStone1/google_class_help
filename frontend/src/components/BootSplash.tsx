import { GraduationCap } from "lucide-react";

/**
 * The neutral screen shown while the first dataset request is in flight.
 *
 * Before this existed, `AppShell` rendered the whole dashboard frame with
 * `SectionSkeleton` placeholders, because `auth` starts as `null` and the
 * landing decision is only made after the first response. A visitor without
 * a session therefore saw a full dashboard — sidebar, top bar, four fake
 * cards — flash for one round trip before the landing appeared, and a deep
 * link to `/settings` flashed the settings page itself.
 *
 * The splash promises nothing but "still loading", which is the only thing
 * that is true yet. It uses the same tokens as everything else, so the
 * theme applied by `theme-init.js` before first paint applies here too.
 */
export function BootSplash() {
  return (
    <div className="boot-splash" role="status" aria-live="polite">
      <div className="boot-splash-logo">
        <GraduationCap size={26} />
      </div>
      <div className="boot-splash-spinner" />
    </div>
  );
}
