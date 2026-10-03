import { act, render, screen } from "@testing-library/react";
import { toast } from "sonner";
import { describe, expect, it } from "vitest";

import { SettingsProvider } from "../../shared/settings/index.ts";
import { DEFAULT_SETTINGS, type ThemeMode } from "../../shared/types/index.ts";
import { Toaster } from "./Toaster.tsx";

/**
 * Sonner itself is rendered here, unlike in `SyncToaster.test.tsx`, which mocks
 * it to test only the decision to announce. The contract worth pinning is the
 * one with `components.css`: the token overrides are keyed on the attributes
 * sonner puts on its region, and those attributes only exist once a toast is
 * actually on screen.
 */
function renderToaster(theme: ThemeMode = "light") {
  localStorage.setItem(
    "gc-settings",
    JSON.stringify({ ...DEFAULT_SETTINGS, language: "en", theme }),
  );
  return render(
    <SettingsProvider>
      <Toaster />
    </SettingsProvider>,
  );
}

async function showToast(): Promise<HTMLElement> {
  await act(async () => {
    toast.success("Synchronization complete", { description: "Just now" });
    await Promise.resolve();
  });
  // Sonner measures each toast in a layout effect, and only renders the
  // positioning attributes once that measurement landed — so the assertion
  // needs one more flushed tick, not just the store update.
  await act(async () => {
    await new Promise((resolve) => setTimeout(resolve, 0));
  });
  const region = document.querySelector<HTMLElement>("[data-sonner-toaster]");
  expect(region).not.toBeNull();
  return region as HTMLElement;
}

describe("Toaster", () => {
  it("mounts a top-right toaster region below the topbar", async () => {
    // The position is a contract with the layout, not a style preference: the
    // bottom-left corner is the sidebar (its "overdue" block is pinned to the
    // bottom), and `top` must clear the topbar so the Sync / bell / theme
    // buttons stay clickable. Both are asserted here because CSS cannot be.
    renderToaster();
    const region = await showToast();

    expect(region).toHaveAttribute("data-x-position", "right");
    expect(region).toHaveAttribute("data-y-position", "top");
    // `var(--toast-top)`, not a raw px value: the token is what lets the same
    // number move when the topbar wraps on narrow screens.
    expect(region.style.getPropertyValue("--offset-top")).toBe(
      "var(--toast-top)",
    );
    expect(screen.getByText("Synchronization complete")).toBeInTheDocument();
  });

  it("follows the app theme instead of keeping a second palette", async () => {
    // The `Sonner toasts` block in components.css keys on exactly this
    // attribute: a mismatch would paint the light palette in dark mode.
    renderToaster("dark");
    const region = await showToast();

    expect(region).toHaveAttribute("data-sonner-theme", "dark");
    expect(document.documentElement.dataset.theme).toBe("dark");
  });

  it("localizes the region label instead of sonner's English default", () => {
    renderToaster();

    // Sonner appends its own hotkey hint to the label, so match the prefix.
    expect(screen.getByLabelText(/^Notifications/)).toBeInTheDocument();
  });
});
