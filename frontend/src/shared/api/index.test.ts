import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { api, setUnauthorizedHandler } from "./index.ts";

const UNAUTHENTICATED = {
  authenticated: false,
  login_in_progress: false,
  error: null,
  auth_url: null,
  user: null,
};

function response(status: number, body: unknown): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    statusText: `status ${status}`,
    json: async () => body,
  } as Response;
}

describe("api session boundary", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn());
  });

  afterEach(() => {
    setUnauthorizedHandler(null);
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it("uses same-origin credentials and injects no Authorization header", async () => {
    vi.mocked(fetch).mockResolvedValue(response(200, UNAUTHENTICATED));

    await api.getAuthStatus();

    const [, init] = vi.mocked(fetch).mock.calls[0];
    expect(init?.credentials).toBe("same-origin");
    expect(new Headers(init?.headers).has("authorization")).toBe(false);
  });

  it("routes a 401 to the registered unauthorized handler", async () => {
    const handler = vi.fn();
    setUnauthorizedHandler(handler);
    vi.mocked(fetch).mockResolvedValue(response(401, { detail: "Not signed in." }));

    await expect(api.getAuthStatus()).rejects.toMatchObject({ status: 401 });
    expect(handler).toHaveBeenCalledTimes(1);
  });

  it("keeps a 405 for the hosted redirect flow instead of treating it as a lost session", async () => {
    const handler = vi.fn();
    setUnauthorizedHandler(handler);
    vi.mocked(fetch).mockResolvedValue(response(405, { detail: "Use GET." }));

    await expect(api.login()).rejects.toMatchObject({ status: 405 });
    expect(handler).not.toHaveBeenCalled();
  });
});
