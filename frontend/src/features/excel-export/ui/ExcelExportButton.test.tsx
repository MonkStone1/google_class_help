import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ExcelExportButton } from "./ExcelExportButton.tsx";
import { SettingsProvider } from "../../../shared/settings/index.ts";
import type { ExportSource } from "../engine/types.ts";

// The dialog must not download a real file; these two modules are the only
// things it does with the workbook, so observing them IS observing the export.
const saveBuffer = vi.hoisted(() => vi.fn());
const buildWorkbookBuffer = vi.hoisted(() =>
  vi.fn(async () => new ArrayBuffer(16)),
);
vi.mock("../engine/download.ts", () => ({ saveBuffer, XLSX_MIME: "text/x" }));
vi.mock("../engine/workbook.ts", () => ({
  buildWorkbookBuffer,
  fillWorksheet: vi.fn(),
}));

function makeSource(overrides: Partial<ExportSource> = {}): ExportSource {
  return {
    id: "w1",
    title: "Урок 15. 20.09.2026 Алгоритми",
    description: "Прочитати https://example.com/test",
    created_at: "2026-09-20T10:00:00",
    course_name: "Математика",
    ...overrides,
  };
}

const TWO = [
  makeSource({ id: "w1", title: "Урок 1. 20.09.2026 Теми" }),
  makeSource({
    id: "w2",
    title: "Урок 2. 21.09.2026 Дроби",
    description: "Розв'язати вправи https://example.com/set",
    created_at: "2026-09-21T10:00:00",
  }),
];

/** English is pinned: the assertions below read the English labels. */
function pinEnglish(): void {
  localStorage.setItem(
    "gc-settings",
    JSON.stringify({ language: "en", theme: "light" }),
  );
}

function renderButton(assignments: readonly ExportSource[] = TWO) {
  pinEnglish();
  // The real provider, not a mocked i18n: the dialog is exactly the component
  // that must be able to read the language the teacher picked.
  return render(
    <SettingsProvider>
      <ExcelExportButton
        courseName="Математика 8/А"
        assignments={assignments}
      />
    </SettingsProvider>,
  );
}

function openDialog(): void {
  fireEvent.click(screen.getByRole("button", { name: /Export to Excel/i }));
}

describe("the export button on the course page", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    buildWorkbookBuffer.mockImplementation(async () => new ArrayBuffer(16));
  });

  it("opens a dialog with the preset, the hint and both buttons", () => {
    renderButton();
    expect(screen.queryByRole("dialog")).toBeNull();

    openDialog();

    expect(
      screen.getByRole("dialog", { name: "Export course to Excel" }),
    ).toBeInTheDocument();
    expect(screen.getByRole("combobox")).toBeInTheDocument();
    expect(
      screen.getByText(/default date is taken from the assignment creation/i),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Cancel" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Export" })).toBeInTheDocument();
  });

  it("previews the rows in order, numbered 1 and 2", () => {
    renderButton();
    openDialog();

    const rows = screen.getAllByRole("row").slice(1);
    expect(rows).toHaveLength(2);
    expect(rows[0]).toHaveTextContent("1");
    expect(rows[1]).toHaveTextContent("2");
  });

  it("previews the CLEANED title and the replaced link", () => {
    renderButton();
    openDialog();

    // What the teacher sees must be what lands in the file, or the preview is
    // decoration rather than a promise.
    expect(screen.getByText("1. Теми")).toBeInTheDocument();
    expect(screen.getByText("Прочитати (google classroom)")).toBeInTheDocument();
    // Every link is replaced, not only the first one.
    expect(screen.getByText("Розв'язати вправи (google classroom)")).toBeInTheDocument();
    expect(screen.queryByText(/https:\/\/example\.com/)).toBeNull();
  });

  it("lets the teacher change a date without touching the assignment itself", () => {
    const assignments = [makeSource()];
    renderButton(assignments);
    openDialog();

    const dateInput = screen.getByLabelText("Date");
    expect(dateInput).toHaveValue("2026-09-20");

    fireEvent.change(dateInput, { target: { value: "2026-10-05" } });

    expect(screen.getByLabelText("Date")).toHaveValue("2026-10-05");
    // The original coursework object keeps its own creation date.
    expect(assignments[0].created_at).toBe("2026-09-20T10:00:00");
  });

  it("saves a workbook under the sanitized course name", async () => {
    renderButton();
    openDialog();

    fireEvent.click(screen.getByRole("button", { name: "Export" }));

    await waitFor(() => expect(buildWorkbookBuffer).toHaveBeenCalledTimes(1));
    expect(saveBuffer).toHaveBeenCalledTimes(1);
    expect(saveBuffer.mock.calls[0][1]).toBe(
      "Математика 8_А_електронний_щоденник.xlsx",
    );
  });

  it("closes on Cancel without building anything", () => {
    renderButton();
    openDialog();

    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));

    expect(screen.queryByRole("dialog")).toBeNull();
    expect(buildWorkbookBuffer).not.toHaveBeenCalled();
  });

  it("closes on Escape, and again after a successful export", async () => {
    renderButton();
    openDialog();
    fireEvent.keyDown(document, { key: "Escape" });
    expect(screen.queryByRole("dialog")).toBeNull();

    openDialog();
    fireEvent.click(screen.getByRole("button", { name: "Export" }));

    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
  });

  it("cannot be pressed at all when the course has no assignments", () => {
    renderButton([]);

    expect(screen.getByRole("button", { name: /Export to Excel/i })).toBeDisabled();
  });
});

describe("errors stay localized and never leak an exception", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    buildWorkbookBuffer.mockRejectedValue(
      new Error("Cannot read properties of undefined (reading 'style')"),
    );
  });

  it("keeps the dialog open and shows a readable message when ExcelJS fails", async () => {
    renderButton();
    openDialog();

    fireEvent.click(screen.getByRole("button", { name: "Export" }));

    await waitFor(() =>
      expect(
        screen.getByText("The Excel file could not be generated."),
      ).toBeInTheDocument(),
    );
    expect(screen.getByRole("dialog")).toBeInTheDocument();
    // The raw stack is for the console, not for the teacher.
    expect(screen.queryByText(/Cannot read properties/)).toBeNull();
  });
});

