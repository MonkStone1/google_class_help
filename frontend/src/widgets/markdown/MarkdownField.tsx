import MDEditor from "@uiw/react-md-editor";
import {
    bold,
    code,
    codeEdit,
    codePreview,
    fullscreen,
    italic,
    link,
    orderedListCommand,
    quote,
    title,
    unorderedListCommand,
    type ICommand,
} from "@uiw/react-md-editor/commands";
// The editor's own stylesheet is imported LOCALLY: the hosted CSP is
// `script-src 'self'; style-src 'self' 'unsafe-inline'` with no CDN and no
// remote origin (main.py, ADR-0026), so a <link> to unpkg/jsdelivr would be
// blocked — and a bundled editor that pulls its CSS from a CDN is simply
// broken in production.
import "@uiw/react-md-editor/markdown-editor.css";
import rehypeSanitize from "rehype-sanitize";

/**
 * The ONE Markdown editor of the application (ADR-0035).
 *
 * Ticket creation, the user's reply and the administrator's answer all render
 * this component: three copies of the toolbar logic would be a defect, not a
 * variation. The toolbar itself is the library's — no hand-rolled buttons.
 *
 * Two rules this wrapper exists to enforce:
 *
 * 1. **Everything rendered is sanitized.** The preview inside the editor AND
 *    the read-only renderer (Markdown.tsx) pass the same `rehypePlugins:
 *    [[rehype-sanitize]]`. Ticket bodies are untrusted input; `rehype-sanitize`
 *    drops `<script>`, event handlers and `javascript:` URLs. Untrusted HTML is
 *    never injected with `dangerouslySetInnerHTML`.
 * 2. **No remote images.** The library's image button is hidden (see TOOLBAR):
 *    a remote image would leak the reader's IP to a third party the moment the
 *    preview renders, and `img-src 'self' data:` would block it anyway.
 *
 * Theme follows the app's own `data-theme` attribute, so light/dark is free.
 *
 * **Edit / Preview is a plain toggle, not an overlay.** `preview="edit"` gives a
 * full-width source field; the library's own `codePreview` button in TOOLBAR
 * (Ctrl/Cmd+9) swaps it for the rendered view, and `codeEdit` (Ctrl/Cmd+7)
 * brings the source back. An earlier attempt overlaid the rendered markdown on
 * a transparent textarea so both were visible at once; it was reverted because
 * the two layers cannot agree on where the caret sits — the caret is laid out by
 * the SOURCE, the visible glyphs by the RENDER, and `**bold**` is eight columns
 * of source over four of text. Two honest states beat one field that lies about
 * where the cursor is.
 */
type Props = {
    value: string;
    onChange: (value: string) => void;
    placeholder?: string;
    minHeight?: number;
    disabled?: boolean;
    /**
     * The id of the underlying textarea. The form pages use it so their
     * `<label htmlFor>` really points at the control — without it the editor is
     * an unlabelled box for anyone reading the page with a screen reader.
     */
    id?: string;
};

/**
 * The toolbar: the library's OWN command objects, in the order a support ticket
 * wants them. Reusing them (instead of hand-rolled buttons) is the point of the
 * wrapper — three copies of toolbar logic would be a defect, not a variation.
 *
 * Deliberately absent: `image`. A remote image would leak the reader's IP to a
 * third party the moment the preview renders, and the CSP's `img-src 'self'
 * data:` would block it anyway — so offering the button would only produce a
 * broken preview.
 *
 * `codePreview` and `codeEdit` are BOTH present on purpose (п.3). Each is the
 * library's own command, so each is one click: Preview (Ctrl/Cmd+9) renders the
 * draft, Edit (Ctrl/Cmd+7) brings the source back. With only `codePreview` the
 * toggle would be one-way — the button would re-dispatch `preview: 'preview'`
 * and the field could never be edited again.
 */
const TOOLBAR: ICommand[] = [
    title,
    bold,
    italic,
    link,
    quote,
    unorderedListCommand,
    orderedListCommand,
    code,
    codePreview,
    codeEdit,
    fullscreen,
];

// The editor's plugin prop is typed for the unified/rehype world; the
// sanitizer is the SAME function the read-only renderer passes, so the preview
// inside the editor and the stored ticket cannot disagree about what is safe.
const PREVIEW_PLUGINS = [[rehypeSanitize]] as never[];

export function MarkdownField({
    value,
    onChange,
    placeholder,
    minHeight = 220,
    disabled = false,
    id,
}: Props) {
    return (
        <div className="markdown-field" data-disabled={disabled || undefined}>
            <MDEditor
                value={value}
                // The library's onChange may hand over `undefined`; the editor's own
                // contract is "the value, or nothing", so an empty string is the right
                // translation for "nothing" and keeps the field a controlled input.
                onChange={(next) => onChange(next ?? "")}
                // The toolbar sits above the text area, so the visual height of the
                // field is larger than this minimum.
                minHeight={minHeight}
                // The preview inside the editor is sanitized with the SAME plugin the
                // read-only renderer uses — a user must not be able to execute anything
                // in their own preview either.
                //
                // `preview="edit"`: the field opens on the source, full width, and
                // the toolbar's Preview/Edit buttons swap the two states. The
                // rendered view is `.wmde-markdown` inside `.w-md-editor-preview`;
                // pages.css themes that class in the app's own tokens.
                preview="edit"
                previewOptions={{
                    rehypePlugins: PREVIEW_PLUGINS,
                }}
                visibleDragbar={false}
                enableScroll={false}
                commands={TOOLBAR}
                // The library takes the placeholder, the accessible name AND the
                // disabled state through the textarea props, not through top-level
                // props (see ITextAreaProps, which extends TextareaHTMLAttributes).
                textareaProps={{
                    id,
                    placeholder,
                    "aria-label": placeholder,
                    disabled,
                }}
            />
        </div>
    );
}
