/**
 * The console page for the administrator registry.
 *
 * Reachable only through `/admin/admins` and guarded by `RequireSuperAdmin`:
 * adding and removing moderators is a super-admin action (ADR-0035), and the
 * guard is named on the route rather than hidden inside the screen.
 */

export { AdminAdmins } from "./ui/AdminAdmins.tsx";