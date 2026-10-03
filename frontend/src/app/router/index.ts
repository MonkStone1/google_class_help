/**
 * The public API of `app/router`.
 *
 * `AppRouter` is the whole of it from the outside: two shells, the route table
 * and the guards around it. Which guards exist is a question about the DOMAIN
 * (`entities/user`), so `routes.tsx` names them by kind (`"admin"`,
 * `"super-admin"`) and this folder decides that "admin" means `RequireAdmin` —
 * the association lives in one file instead of in every route entry.
 */

export { AppRouter } from "./AppRouter.tsx";
export { ADMIN_ROUTES, USER_ROUTES } from "./routes.tsx";
export type { Guard, RouteDefinition } from "./routes.tsx";