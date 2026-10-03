/**
 * The settings screen: language, theme, default sort and card density.
 *
 * Everything here writes through `shared/settings`, which persists to
 * localStorage — a setting that is forgotten on reload is not a setting.
 */

export { Settings } from "./ui/Settings.tsx";