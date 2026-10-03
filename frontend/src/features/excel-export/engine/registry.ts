import type { ExportPreset, PresetId } from "./types.ts";

/**
 * The preset registry (ADR-0041).
 *
 * A map, not a switch: adding a preset is `registerPreset(preset)` next to its
 * file, and nothing in the engine, the tests or the page changes with it. The
 * one thing that must be loud is an unknown id — a silent fallback would export
 * the WRONG file format under a name the teacher picked, which is exactly the
 * failure a preset system exists to prevent.
 */

const REGISTRY = new Map<PresetId, ExportPreset>();

/** Add a preset, replacing any earlier one with the same id. */
export function registerPreset(preset: ExportPreset): void {
  REGISTRY.set(preset.id, preset);
}

/** Whether `id` names a registered preset. */
export function isPresetId(id: string): id is PresetId {
  return REGISTRY.has(id);
}

/**
 * The preset for `id`, or a thrown error.
 *
 * Throwing rather than returning `null` keeps every caller's failure path
 * identical: the caller is already inside a try/catch that shows a localized
 * message, and a `null` would have to be checked twice — once here, once there.
 */
export function getPreset(id: PresetId): ExportPreset {
  const preset = REGISTRY.get(id);
  if (!preset) {
    throw new Error(`Unknown export preset: ${id}`);
  }
  return preset;
}

/** Every registered preset, in registration order. */
export function listPresets(): ExportPreset[] {
  return [...REGISTRY.values()];
}

/** Drops every registration; tests use it to stay independent of each other. */
export function clearPresets(): void {
  REGISTRY.clear();
}