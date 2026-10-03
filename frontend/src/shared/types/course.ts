import type { Wire } from "./wire.ts";

/**
 * Role of the signed-in user in a particular course.
 *
 * It belongs HERE rather than in `assignment.ts` because it is a property of a
 * course, and both an assignment and a course card carry it: the "Teacher" badge
 * on a subject is what says the user may open its grade matrix. Keeping it in
 * the course module also keeps the dependency one-directional
 * (assignment -> course), so `course.ts` imports nothing from `assignment.ts`.
 */
export type UserRole = "TEACHER" | "STUDENT";

export type Course = Omit<Wire<"CourseOut">, "role"> & {
    role: UserRole;
};

export type CourseDetail = Omit<Wire<"CourseDetailOut">, "role"> & {
    role: UserRole;
};