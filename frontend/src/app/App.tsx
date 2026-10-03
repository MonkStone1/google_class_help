/**
 * The application root: providers, the sign-in gate, and the routed shell.
 *
 * It was 284 lines — the two `<Routes>` blocks, both shells, the session gate
 * and the search plumbing — and is now a decision tree over a pure function
 * plus the router. Everything with a name lives in a file of its own:
 * `boot/bootGate.ts` says which surface, `router/routes.tsx` says which pages,
 * `router/AppRouter.tsx` picks the shell from the matched route and builds the
 * elements, `layouts/` are the two shells.
 *
 * The order matters and is easy to get wrong: the gate must run INSIDE the
 * providers, because it reads the auth answer the data provider owns.
 */

import { useRef } from "react";

import { BootSplash, bootSurface } from "./boot/index.ts";
import { AppProviders } from "./providers/index.ts";
import { AppRouter } from "./router/index.ts";
import { Landing, SignIn } from "../widgets/landing/index.ts";
import { useAuth } from "../entities/user/index.ts";

export default function App() {
  return (
    <AppProviders>
      <AppGate />
    </AppProviders>
  );
}

/** Splash, landing, sign-in gate — or the routed shell. */
function AppGate() {
  const { auth, sessionRequired } = useAuth();

  // A browser that never had a session should meet the public landing page, not
  // a bare login card; a browser whose session merely EXPIRED already knows the
  // site and only needs the way back in (ADR-0029). The ref, not state: the
  // distinction is read during render and must not re-render.
  const hadSession = useRef(false);
  if (auth?.authenticated) {
    hadSession.current = true;
  }

  const surface = bootSurface({
    auth,
    sessionRequired,
    hadSession: hadSession.current,
  });

  switch (surface) {
    // Before `BootSplash` existed this rendered the whole dashboard frame with
    // skeletons, and a visitor without a session saw a full product flash for
    // one round trip before the landing appeared.
    case "splash":
      return <BootSplash />;
    case "landing":
      return <Landing />;
    case "sign-in":
      return <SignIn />;
    case "shell":
      return <AppRouter />;
  }
}