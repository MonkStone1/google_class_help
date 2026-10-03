/**
 * The public API of the transport layer: one `api` object, assembled from the
 * endpoint groups.
 *
 * This facade is why callers write `api.getMyTicket(id)` instead of importing
 * seven modules. It is deliberately thin — the behaviour lives in
 * `endpoints/*.ts`, the fetch conventions in `client.ts` — because a facade that
 * grows logic becomes the god object this restructure was meant to remove
 * (ADR-0040 §3.3).
 *
 * `vi.mock("../shared/api/index.ts")` replaces THIS module: tests mock the
 * facade, not the eight groups, so a new endpoint does not mean a new mock.
 */

import { admin } from "./endpoints/admin.ts";
import { assignments } from "./endpoints/assignments.ts";
import { auth } from "./endpoints/auth.ts";
import { courses } from "./endpoints/courses.ts";
import { feedback } from "./endpoints/feedback.ts";
import { grades } from "./endpoints/grades.ts";
import { status } from "./endpoints/status.ts";
import { sync } from "./endpoints/sync.ts";

export {
    LOGIN_URL,
    setUnauthorizedHandler,
    type ApiError,
    type TurnstileConfig,
} from "./client.ts";

export const api = {
    ...auth,
    ...status,
    ...sync,
    ...courses,
    ...assignments,
    ...grades,
    ...feedback,
    ...admin,
};