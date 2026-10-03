import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { Landing } from "./Landing.tsx";
import { SettingsProvider } from "../../shared/settings/SettingsProvider.tsx";
import { DEFAULT_SETTINGS } from "../../shared/types/index.ts";
import type { Language } from "../../shared/types/index.ts";

const login = vi.fn();
const setLanguage = vi.fn();
const setTheme = vi.fn();
let currentLanguage: Language = "en";

vi.mock("../../entities/user/index.ts", () => ({
  useAuth: () => ({ login }),
}));

vi.mock("../../shared/settings/SettingsProvider.tsx", async () => {
  const actual = await vi.importActual<
    typeof import("../../shared/settings/SettingsProvider.tsx")
  >("../../shared/settings/SettingsProvider.tsx");
  // Only the hook is driven from here; the real provider still wraps the
  // page, so the select is rendered by the same code the app uses.
  return {
    ...actual,
    useSettings: () => ({
      language: currentLanguage,
      setLanguage,
      setTheme,
    }),
  };
});

// The challenge hook owns a network call; the landing's own contract is what
// is under test, so the hook is driven from here.
const useSignInChallenge = vi.fn();
vi.mock("./useSignInChallenge.ts", () => ({
  useSignInChallenge: () => useSignInChallenge(),
}));

function noChallenge() {
  return {
    token: null,
    required: false,
    requested: false,
    pending: false,
    widgetRef: { current: null },
  };
}

function renderLanding(language: Language) {
  // The mocked `useSettings` is the single source of `language` for the
  // rendered strings, so the value has to be set before render — reading the
  // language back out of localStorage (as the real provider does) would fight
  // the mock. The real provider still wraps the page and still reads storage
  // for itself, so the two are seeded together: the document language is the
  // provider's to set now, not the landing's (ADR-0034).
  currentLanguage = language;
  localStorage.setItem(
    "gc-settings",
    JSON.stringify({ ...DEFAULT_SETTINGS, language }),
  );
  return render(
    <SettingsProvider>
      <Landing />
    </SettingsProvider>,
  );
}

describe("Landing", () => {
  beforeEach(() => {
    login.mockReset();
    setLanguage.mockReset();
    setTheme.mockReset();
    useSignInChallenge.mockReset();
    useSignInChallenge.mockReturnValue(noChallenge());
  });

  it("explains the site and links to the privacy policy", () => {
    renderLanding("uk");

    expect(
      screen.getByRole("heading", {
        name: "Ваш Google Classroom на одному екрані",
      }),
    ).toBeInTheDocument();
    expect(screen.getByText("Що це за сайт")).toBeInTheDocument();
    expect(screen.getByText("Що він уміє")).toBeInTheDocument();
    expect(screen.getByText("Як це працює")).toBeInTheDocument();
    expect(screen.getByText("Ваші дані")).toBeInTheDocument();

    // The privacy page is a STATIC file outside the SPA router, so it must
    // be a plain anchor to the real path — a router link would render the
    // dashboard shell instead of the document.
    const privacy = screen.getAllByRole("link", {
      name: /Політика конфіденційності/,
    });
    expect(privacy.length).toBeGreaterThan(0);
    for (const link of privacy) {
      expect(link).toHaveAttribute("href", "/privacy/");
    }
  });

  it("renders in the stored language", () => {
    renderLanding("en");
    expect(
      screen.getByRole("heading", {
        name: "Your Google Classroom in one place",
      }),
    ).toBeInTheDocument();

    renderLanding("ru");
    expect(
      screen.getAllByRole("heading", {
        name: "Ваш Google Classroom на одном экране",
      }).length,
    ).toBeGreaterThan(0);
  });

  it("offers sign-in in the header and again after the information", () => {
    renderLanding("uk");

    const buttons = screen.getAllByRole("button", {
      name: /Увійти через Google/,
    });
    // Two entry points: the sticky header and the closing call to action.
    expect(buttons).toHaveLength(2);
  });

  it("starts the sign-in flow from either button", () => {
    renderLanding("uk");

    const [header] = screen.getAllByRole("button", {
      name: /Увійти через Google/,
    });
    fireEvent.click(header);

    expect(login).toHaveBeenCalledTimes(1);
  });

  it("passes the solved challenge token to the sign-in call", () => {
    useSignInChallenge.mockReturnValue({
      ...noChallenge(),
      token: "solved-token",
      required: true,
    });
    renderLanding("uk");

    fireEvent.click(
      screen.getAllByRole("button", { name: /Увійти через Google/ })[0],
    );

    expect(login).toHaveBeenCalledWith("solved-token");
  });

  it("does not start a login while the challenge is still unsolved", () => {
    useSignInChallenge.mockReturnValue({
      ...noChallenge(),
      required: true,
      pending: true,
    });
    // jsdom implements no layout, so scrolling does not exist there.
    const scrollIntoView = vi.fn();
    Element.prototype.scrollIntoView = scrollIntoView;
    renderLanding("uk");

    // The buttons stay clickable on purpose: the click scrolls the widget
    // into view instead of firing a request the server would reject.
    const [header] = screen.getAllByRole("button", {
      name: /Увійти через Google/,
    });
    expect(header).not.toBeDisabled();
    fireEvent.click(header);

    expect(login).not.toHaveBeenCalled();
    expect(scrollIntoView).toHaveBeenCalled();
  });

  it("shows the widget only when the server requires a challenge", () => {
    const { rerender } = renderLanding("uk");
    expect(
      screen.queryByText(/Пройдіть перевірку нижче/),
    ).not.toBeInTheDocument();

    useSignInChallenge.mockReturnValue({
      ...noChallenge(),
      required: true,
      pending: true,
    });
    rerender(
      <SettingsProvider>
        <Landing />
      </SettingsProvider>,
    );

    expect(
      screen.getByText(/Пройдіть перевірку нижче/),
    ).toBeInTheDocument();
  });

  it("switches the language from the header", async () => {
    renderLanding("uk");

    fireEvent.change(screen.getByRole("combobox"), {
      target: { value: "ru" },
    });

    await waitFor(() => expect(setLanguage).toHaveBeenCalledWith("ru"));
  });

  it("offers NO donation codes to a visitor with no session", () => {
    // п.9 reverses half of ADR-0037. The landing's job is to explain the site
    // and get the visitor through Google sign-in; a payment QR pair in the
    // middle of that flow interrupts the one action the page exists to offer,
    // and asks a stranger for money before they have seen the product work.
    // Support is asked of signed-in users instead, in `/settings`.
    renderLanding("uk");

    expect(
      screen.queryByRole("heading", { name: "Підтримати проєкт" }),
    ).not.toBeInTheDocument();
    // The component itself is untouched — only this entry point is gone, and
    // the enlarged-code control is the tell-tale that the block is absent.
    expect(
      screen.queryByRole("button", { name: "Збільшити QR-код Monobank" }),
    ).not.toBeInTheDocument();
    expect(document.querySelector(".donate")).toBeNull();
    // The rest of the page is untouched: the sign-in CTA is still there.
    expect(
      screen.getAllByRole("button", { name: /Увійти через Google/ }).length,
    ).toBeGreaterThan(0);
  });

  it("leaves the document language to the settings provider", () => {
    // The landing used to own `<html lang>` on its own (ADR-0029), which meant
    // the attribute only ever followed the language on THIS surface. The
    // provider owns it now, so the landing must not overwrite it (ADR-0034).
    renderLanding("uk");
    expect(document.documentElement.lang).toBe("uk");
  });
});
