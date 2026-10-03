/**
 * The public API of the type layer.
 *
 * `shared/types/` is split by DOMAIN, not by size: a reader looking for "what
 * is a FeedbackTicket" opens one file and finds every ticket type, and the file
 * that talks to the generated schema (`wire.ts`) is the only one that knows the
 * schema exists. The split could not happen before because this module was
 * imported by more than fifty files — the facade makes it invisible.
 *
 * Importing from `./shared/types/index.ts` rather than from a domain file is not
 * a style preference: it is what allows a type to move between domains without
 * touching a single caller, and it is guardrail #10 in
 * `src/test/structure.test.ts`.
 */

export * from "./assignment.ts";
export * from "./course.ts";
export * from "./feedback.ts";
export * from "./grades.ts";
export * from "./ui.ts";
export * from "./user.ts";

// `wire.ts` is not re-exported wholesale: `Schemas`, `DeepRequired` and
// `Wire<…>` are the mechanics of reading the generated schema, and a caller
// that needs a raw wire shape should say which one it wants rather than inherit
// the whole vocabulary. `WithStatus` stays internal to the domain modules for
// the same reason — it is a transformation, not a type the UI names.
export type {} from "./wire.ts";