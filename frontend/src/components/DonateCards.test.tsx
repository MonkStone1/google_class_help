import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { SettingsProvider } from "../context/SettingsContext.tsx";
import { DEFAULT_SETTINGS, type Language } from "../types.ts";
import { DonateCards } from "./DonateCards.tsx";

function renderCards(language: Language = "en") {
  localStorage.setItem(
    "gc-settings",
    JSON.stringify({ ...DEFAULT_SETTINGS, language }),
  );
  return render(
    <SettingsProvider>
      <DonateCards />
    </SettingsProvider>,
  );
}

describe("DonateCards", () => {
  it("shows where the money goes, in the interface language", () => {
    renderCards("en");
    expect(
      screen.getByText("This money goes to keeping the project running and developing it."),
    ).toBeInTheDocument();

    renderCards("ru");
    expect(
      screen.getAllByText(
        "Эти деньги пойдут на поддержание и развитие проекта.",
      ).length,
    ).toBeGreaterThan(0);
  });

  it("renders one code per bank, each reachable and named", () => {
    // The regression this pins: dropping a bank would silently remove a way to
    // donate, and an unnamed control would leave the feature unreachable for
    // anyone not using a mouse. The bank name lives on the BUTTON, not on the
    // thumbnail `alt` — inside a labelled button a second copy of the same
    // text would only be announced twice.
    renderCards("en");

    const controls = document.querySelectorAll(".donate-open");
    expect(controls).toHaveLength(2);
    const thumbs = document.querySelectorAll("img.donate-qr");
    expect(thumbs).toHaveLength(2);
    expect(
      document.querySelector('img[src="/donate/monobank.png"]'),
    ).toBeInTheDocument();
    expect(
      document.querySelector('img[src="/donate/privatbank.png"]'),
    ).toBeInTheDocument();
  });

  it("serves the codes from the same origin as the app", () => {
    // CSP is `img-src 'self' data:` (§48) and the hosting decision is
    // one-public-origin (ADR-0025): a code behind another domain would render
    // as a broken image for every visitor, and the test would still pass.
    renderCards("en");
    for (const code of document.querySelectorAll("img.donate-qr")) {
      expect(code.getAttribute("src")).toMatch(/^\/donate\/[a-z]+\.png$/);
    }
  });

  it("declares the real pixel size of each artwork, so the QR is not stretched", () => {
    // The real files are 1051×1280 and 1056×1280 — portrait, and different from
    // each other. Declaring a square (or equal sizes for both) would make the
    // browser reserve the wrong box and, before `height: auto` was in the CSS,
    // physically stretch the code past the point a bank app can read it.
    renderCards("en");

    const mono = document.querySelector<HTMLImageElement>(
      'img[src="/donate/monobank.png"].donate-qr',
    );
    const privat = document.querySelector<HTMLImageElement>(
      'img[src="/donate/privatbank.png"].donate-qr',
    );
    expect([mono?.getAttribute("width"), mono?.getAttribute("height")]).toEqual([
      "1051",
      "1280",
    ]);
    expect([privat?.getAttribute("width"), privat?.getAttribute("height")]).toEqual([
      "1056",
      "1280",
    ]);
  });

  it("offers each code as a button that enlarges it", () => {
    // A bare image would be inert: no keyboard access and nothing announced.
    renderCards("en");
    expect(
      screen.getByRole("button", { name: "Enlarge the Monobank QR code" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Enlarge the PrivatBank QR code" }),
    ).toBeInTheDocument();
  });

  it("opens the full-size artwork and closes it again", () => {
    renderCards("en");
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();

    fireEvent.click(
      screen.getByRole("button", { name: "Enlarge the Monobank QR code" }),
    );

    const dialog = screen.getByRole("dialog");
    expect(dialog).toBeInTheDocument();
    // The enlarged view is the same served file — enlarging must not mean
    // fetching a different or lower-quality asset. Scoped to the dialog,
    // because the thumbnail is still in the DOM behind it.
    const enlarged = dialog.querySelector("img.donate-preview-image");
    expect(enlarged).toHaveAttribute("src", "/donate/monobank.png");
    // The enlarged copy is the only description of that image, so unlike the
    // thumbnail it keeps a real alt.
    expect(enlarged).toHaveAttribute("alt", "Donation QR code for Monobank");

    fireEvent.click(screen.getByRole("button", { name: "Close" }));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("closes the enlarged view with Escape and returns focus to the code", () => {
    // The focus return is the part that matters: without it, dismissing with
    // the keyboard drops the reader at the top of the document.
    renderCards("en");
    const trigger = screen.getByRole("button", {
      name: "Enlarge the PrivatBank QR code",
    });

    fireEvent.click(trigger);
    fireEvent.keyDown(document, { key: "Escape" });

    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(document.activeElement).toBe(trigger);
  });

  it("leaves the artwork itself unstyled, so the code keeps scanning", () => {
    // The banks ship their QR on their own background. A white plate, a tint or
    // an inline `filter` on the image would stop it scanning, so the <img> must
    // carry no presentation of its own — the theme is carried by the card
    // AROUND it. The matching stylesheet rule is asserted in
    // tests/test_stage8_coexistence.py, which can read the CSS; Vitest does not
    // load the app's stylesheets, so a computed-style check here would pass
    // without ever looking at the rule.
    const { container } = renderCards("en");
    for (const code of container.querySelectorAll<HTMLElement>(".donate-qr")) {
      expect(code.getAttribute("style")).toBeNull();
      expect(code.className).toBe("donate-qr");
    }
  });
});
