/**
 * The locally cached Classroom slice, as the pages read it.
 *
 * Kept apart from `useAuth` for the reason the three contexts were split in the
 * first place (ADR-0040 §1.4): subscribing to this one re-renders only when
 * courses or assignments change, while a sync spinner or a session answer does
 * not touch every list on the screen.
 */

import { createContext } from "react";

import type { Assignment, Course } from "../../../shared/types/index.ts";
import { useContextSafe } from "../../user/index.ts";

/**
 * The locally cached Classroom slice. Changes on a sync or a manual refresh.
 */
export type CoursesState = {
  courses: Course[];
  assignments: Assignment[];
};

export const CoursesContext = createContext<CoursesState | null>(null);

export function useCourses(): CoursesState {
  return useContextSafe(CoursesContext, "useCourses");
}