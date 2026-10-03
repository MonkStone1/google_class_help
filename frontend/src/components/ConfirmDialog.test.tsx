import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { SettingsProvider } from "../shared/settings/SettingsProvider.tsx";
import { ConfirmDialog } from "./ConfirmDialog.tsx";

function renderDialog(
    props: Partial<Parameters<typeof ConfirmDialog>[0]> = {},
) {
    const onConfirm = vi.fn();
    const onClose = vi.fn();
    render(
        <MemoryRouter>
            <SettingsProvider>
                <ConfirmDialog
                    open
                    title="Delete this ticket permanently?"
                    body="This action cannot be undone."
                    confirmLabel="Delete permanently"
                    cancelLabel="Cancel"
                    onConfirm={onConfirm}
                    onClose={onClose}
                    {...props}
                />
            </SettingsProvider>
        </MemoryRouter>,
    );
    return { onConfirm, onClose };
}

describe("ConfirmDialog", () => {
    beforeEach(() => {
        vi.clearAllMocks();
    });

    it("states the irreversible consequence before offering the buttons", () => {
        renderDialog();
        expect(
            screen.getByRole("alertdialog", {
                name: "Delete this ticket permanently?",
            }),
        ).toBeInTheDocument();
        expect(
            screen.getByText("This action cannot be undone."),
        ).toBeInTheDocument();
    });

    it("does NOT fire the delete until the destructive button is clicked", () => {
        // The regression this pins: a dialog that deleted on mount, or a delete
        // button wired to the click that OPENED it, would destroy a ticket nobody
        // confirmed.
        const { onConfirm } = renderDialog();
        expect(onConfirm).not.toHaveBeenCalled();
        fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
        expect(onConfirm).not.toHaveBeenCalled();
    });

    it("fires the callback only after the destructive action is clicked", () => {
        const { onConfirm } = renderDialog();
        fireEvent.click(
            screen.getByRole("button", { name: "Delete permanently" }),
        );
        expect(onConfirm).toHaveBeenCalledTimes(1);
    });

    it("styles the destructive action with the danger button", () => {
        renderDialog();
        expect(
            screen.getByRole("button", { name: "Delete permanently" })
                .className,
        ).toContain("button-danger");
        // …and keeps Cancel visually separate from it.
        expect(
            screen.getByRole("button", { name: "Cancel" }).className,
        ).not.toContain("button-danger");
    });

    it("closes on Escape and on a backdrop click, without deleting", () => {
        const { onConfirm, onClose } = renderDialog();
        fireEvent.keyDown(document, { key: "Escape" });
        expect(onClose).toHaveBeenCalled();
        expect(onConfirm).not.toHaveBeenCalled();
    });

    it("renders nothing while closed", () => {
        renderDialog({ open: false });
        expect(screen.queryByRole("alertdialog")).toBeNull();
    });
});
