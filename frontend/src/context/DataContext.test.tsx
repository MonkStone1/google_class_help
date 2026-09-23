import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { setUnauthorizedHandler } from "../api.ts";
import { DataProvider, useAuth } from "./DataContext.tsx";

function Probe() {
  const { auth, sessionRequired } = useAuth();
  const label = sessionRequired
    ? "gate"
    : auth?.authenticated
      ? "signed-in"
      : "signed-out";
  return <span data-testid="probe">{label}</span>;
}

function unauthorizedResponse(): Response {
  return {
    ok: false,
    status: 401,
    statusText: "Unauthorized",
    json: async () => ({ detail: "Not signed in." }),
  } as Response;
}

describe("DataProvider 401 handling", () => {
  beforeEach(() => {
    vi.stubGlobal(
      "fetch",
      vi.fn(() => Promise.resolve(unauthorizedResponse())),
    );
  });

  afterEach(() => {
    setUnauthorizedHandler(null);
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it("moves to the sign-in gate when the session is rejected", async () => {
    render(
      <DataProvider>
        <Probe />
      </DataProvider>,
    );

    await waitFor(() =>
      expect(screen.getByTestId("probe")).toHaveTextContent("gate"),
    );
  });
});
