import type { MutableRefObject } from "react";
import { useEffect, useRef, useState } from "react";

import { api } from "../api.ts";
import type { TurnstileConfig } from "../api.ts";

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

/** What a caller needs in order to render a sign-in surface. */
export type SignInChallenge = {
  /** The solved widget token, or null while no challenge is pending. */
  token: string | null;
  /** The server requires a widget before a sign-in may start. */
  required: boolean;
  /** The server bounced the browser back with `?challenge=required`. */
  requested: boolean;
  /** A challenge is required but not solved yet. */
  pending: boolean;
  /** Attach to the element the widget should be rendered into. */
  widgetRef: MutableRefObject<HTMLDivElement | null>;
};

/**
 * The Cloudflare Turnstile challenge that guards login initiation
 * (DDoS plan §17, stage 10).
 *
 * Shared by the two surfaces that can start a sign-in — the compact `SignIn`
 * gate and the public `Landing` page — so the widget is loaded and solved
 * once and both entry points read the same token.
 *
 * The secret key stays on the backend; the browser sees only the public
 * site key. A failing config request means "no challenge" (the default)
 * rather than an error state: sign-in must stay usable even when the widget
 * service cannot be reached.
 */
export function useSignInChallenge(): SignInChallenge {
  const widgetRef = useRef<HTMLDivElement | null>(null);
  const [turnstile, setTurnstile] = useState<TurnstileConfig | null>(null);
  const [token, setToken] = useState<string | null>(null);
  const requested =
    new URLSearchParams(window.location.search).get("challenge") === "required";

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

  // Load the widget script once and render it into the given container.
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

  const required = Boolean(turnstile?.enabled);
  return { token, required, requested, pending: required && token === null, widgetRef };
}
