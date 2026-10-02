import MDEditor from "@uiw/react-md-editor";
import rehypeSanitize from "rehype-sanitize";

// The library types its rehype prop for the unified world; the sanitizer is the
// SAME function the editor passes, so the preview and the stored ticket cannot
// disagree about what is safe.
const SANITIZE_PLUGINS = [[rehypeSanitize]] as never[];

/**
 * Read-only rendering of stored Markdown (ADR-0035).
 *
 * Ticket bodies are UNTRUSTED INPUT: they are stored verbatim by the backend
 * and sanitized here, at render time, by the same plugin the editor's preview
 * uses. There is no `dangerouslySetInnerHTML` anywhere in this path — the
 * library builds real React elements, so a `<script>` in a ticket body becomes
 * text, not code.
 *
 * `MDEditor.Markdown` is the library's read-only component; using it here keeps
 * one Markdown pipeline (one set of plugins, one theme) for editing and for
 * reading, instead of two that could disagree about what is safe.
 */
export function Markdown({ children }: { children: string }) {
    return (
        <div className="markdown-body">
            {/* No `theme` prop: the library has no theme prop of its own here, and
          forcing light/dark from JS would fight the app's `<html data-theme>`
          switch. `.markdown-body` in styles/pages.css repaints the preview in
          the app's own tokens, which is why the theme follows for free. */}
            <MDEditor.Markdown
                source={children}
                rehypePlugins={SANITIZE_PLUGINS}
            />
        </div>
    );
}
