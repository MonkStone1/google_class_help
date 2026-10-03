import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";

import { SettingsProvider } from "../../shared/settings/index.ts";
import { MarkdownField } from "./MarkdownField.tsx";

function renderField(value: string) {
    const { container } = render(
        <MemoryRouter>
            <SettingsProvider>
                <MarkdownField
                    value={value}
                    onChange={() => {}}
                    placeholder="Write your reply…"
                />
            </SettingsProvider>
        </MemoryRouter>,
    );
    return container;
}

/**
 * The one Markdown editor (ADR-0035), after п.3.
 *
 * Two contracts are asserted here, and neither is about looks:
 *
 * 1. **Edit and Preview are two honest states.** The field opens on the source
 *    at full width and the toolbar carries the library's own `codePreview` /
 *    `codeEdit` commands. The defect this replaces was `preview="live"`: a 50/50
 *    split that showed raw Markdown beside a preview. An intermediate attempt
 *    overlaid the rendered text on a transparent textarea to show both at once;
 *    it was reverted because the caret is laid out by the source while the
 *    visible glyphs come from the render, so the cursor drifts the moment any
 *    markup is present.
 *
 * 2. **The preview is sanitized.** It comes from the same `rehype-sanitize`
 *    pipeline as the read-only renderer, so a `<script>` in a draft body must
 *    not survive as live markup in the editor's own preview.
 *
 * What is deliberately NOT asserted: any inline `style` on the preview, or the
 * background colour. Vitest does not load the app's stylesheets, so a computed
 * style check would pass without reading the rule it claims to verify — the
 * `.wmde-markdown` theming is a CSS-file concern, pinned where the CSS is
 * actually read.
 */
describe("MarkdownField", () => {
    it("opens on the source, full width, and toggles to Preview and back", async () => {
        const container = renderField("**bold** and `code`");

        // EDIT is the opening state: a full-width source column and no rendered
        // column beside it. The defect this replaces was `preview="live"`, which
        // split the field 50/50 and showed raw Markdown next to a narrow preview
        // nobody asked for.
        await waitFor(() => {
            expect(
                container.querySelector(".w-md-editor")?.className,
            ).toContain("w-md-editor-show-edit");
        });

        // The source textarea holds the raw Markdown — this is what every
        // toolbar command edits.
        expect(container.querySelector("textarea")).toHaveValue(
            "**bold** and `code`",
        );

        // Both halves of the toggle exist and are named by the library.
        //
        // Queried by `data-name`, not by role+name: the library renders the
        // toolbar TWICE (a visible row and a `warpperElement` copy that only
        // shows on narrow screens), so every toolbar button matches twice and a
        // role query throws "found multiple elements".
        const toggle = (name: "preview" | "edit") =>
            container.querySelector<HTMLButtonElement>(
                `button[data-name="${name}"]`,
            )!;
        const preview = toggle("preview");
        const edit = toggle("edit");
        expect(preview).not.toBeNull();
        expect(edit).not.toBeNull();
        expect(preview.getAttribute("aria-label")).toMatch(/preview/i);
        expect(edit.getAttribute("aria-label")).toMatch(/edit/i);

        // Pressing Preview switches the surface…
        fireEvent.click(preview);
        await waitFor(() => {
            expect(
                container.querySelector(".w-md-editor")?.className,
            ).toContain("w-md-editor-show-preview");
        });
        // …and the rendered column carries the text as markup.
        await waitFor(() => {
            const rendered = container.querySelector(
                ".w-md-editor-preview .wmde-markdown",
            );
            expect(rendered).not.toBeNull();
            expect(rendered!.querySelector("strong")?.textContent).toBe("bold");
        });

        // Pressing Edit brings the source back: a one-way switch would strand
        // the writer in a read-only view with no way out but reloading.
        fireEvent.click(edit);
        await waitFor(() => {
            expect(
                container.querySelector(".w-md-editor")?.className,
            ).toContain("w-md-editor-show-edit");
        });
    });

    it("renders the preview with the same sanitizer as the read-only view", async () => {
        const container = renderField("<script>alert(1)</script>");

        fireEvent.click(
            container.querySelector<HTMLButtonElement>(
                'button[data-name="preview"]',
            )!,
        );
        await waitFor(() => {
            const rendered = container.querySelector(
                ".w-md-editor-preview .wmde-markdown",
            );
            expect(rendered).not.toBeNull();
            // Scoped to the RENDERED column, deliberately. The textarea holds the
            // raw source and MUST contain that text — it is the draft being
            // edited, and it is inert there.
            expect(rendered!.querySelector("script")).toBeNull();
            expect(rendered!.innerHTML).not.toContain("alert(1)");
        });
    });

    it("drops the editable source while Preview is showing", async () => {
        // The library renders the textarea only for `edit` and `live`
        // (`Editor.factory.js`: `/(edit|live)/.test(state.preview)`), so in
        // `preview` state there is nothing to type into. That is the honest
        // reason the two modes are separate: pressing Preview shows a finished
        // rendering, and Edit brings the source back with the caret where it
        // was left.
        const container = renderField("**bold**");

        expect(container.querySelector("textarea")).not.toBeNull();

        fireEvent.click(
            container.querySelector<HTMLButtonElement>(
                'button[data-name="preview"]',
            )!,
        );

        await waitFor(() => {
            expect(container.querySelector("textarea")).toBeNull();
            expect(
                container.querySelector(".w-md-editor")?.className,
            ).toContain("w-md-editor-show-preview");
        });
    });

    it("labels the textarea so the field is reachable without a mouse", () => {
        // The placeholder doubles as the accessible name. The reply panel that
        // owns this editor may be collapsed, and an unlabelled box would be
        // invisible to anyone navigating by screen reader.
        renderField("");
        expect(
            screen.getByLabelText(/write your reply/i, { selector: "textarea" }),
        ).toBeInTheDocument();
    });
});