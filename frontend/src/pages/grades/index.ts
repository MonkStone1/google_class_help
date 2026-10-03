/**
 * One student's grades across every course.
 *
 * A single table rather than one table per course: the question a parent or a
 * student asks is "how am I doing overall", and per-course tables answer it
 * only by summing columns in their head.
 */

export { Grades } from "./ui/Grades.tsx";