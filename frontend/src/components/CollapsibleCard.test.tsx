import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { SettingsProvider } from "../context/SettingsContext.tsx";
import { DEFAULT_SETTINGS } from "../types.ts";
import { CollapsibleCard } from "./CollapsibleCard.tsx";

function renderCard(
  props: Partial<Parameters<typeof CollapsibleCard>[0]> = {},
): void {
  localStorage.setItem(
    "gc-settings",
    JSON.stringify({ ...DEFAULT_SETTINGS, language: "en" }),
  );
  render(
    <SettingsProvider>
      <CollapsibleCard title="Support the project" {...props}>
        <p>The donation body.</p>
      </CollapsibleCard>
    </SettingsProvider>,
  );
}

describe("CollapsibleCard", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("starts collapsed, so the body costs nothing until it is asked for", () => {
    // The reason this component exists (ADR-0037): the support block must not
    // push the settings a user actually came for down the page.
    renderCard();
    expect(screen.queryByText("The donation body.")).not.toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Support the project" }),
    ).toHaveAttribute("aria-expanded", "false");
  });

  it("reveals and hides the body on each click", () => {
    renderCard();
    const toggle = screen.getByRole("button", { name: "Support the project" });

    fireEvent.click(toggle);
    expect(screen.getByText("The donation body.")).toBeInTheDocument();
    expect(toggle).toHaveAttribute("aria-expanded", "true");

    fireEvent.click(toggle);
    expect(screen.queryByText("The donation body.")).not.toBeInTheDocument();
  });

  it("points aria-controls at the body it actually toggles", () => {
    // An `aria-controls` naming an id that is absent from the DOM is worse
    // than none: the control is announced as broken.
    renderCard();
    const toggle = screen.getByRole("button", { name: "Support the project" });
    const bodyId = toggle.getAttribute("aria-controls");
    expect(bodyId).toBeTruthy();

    fireEvent.click(toggle);
    const body = document.getElementById(bodyId as string);
    expect(body).toBeInTheDocument();
    expect(body).toHaveTextContent("The donation body.");
  });

  it("can start expanded when a caller asks for it", () => {
    renderCard({ defaultOpen: true });
    expect(screen.getByText("The donation body.")).toBeInTheDocument();
  });
});
