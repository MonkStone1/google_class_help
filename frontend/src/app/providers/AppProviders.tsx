/**
 * The provider stack, in the order the app needs it.
 *
 * Settings first because `useI18n` reads the language from it, and the data
 * provider renders translated error strings. The toast host sits here, next to
 * the shell and not inside it: the shell returns early for the splash, the
 * landing and the sign-in gate, and a sync that finishes in the background must
 * be announced on the surface the user actually came back to. `<Toaster />` needs
 * the settings (theme), `<SyncToaster />` the sync state.
 */

import type { ReactNode } from "react";

import { SettingsProvider } from "../../shared/settings/index.ts";
import { DataProvider } from "./DataProvider.tsx";
import { SyncToaster, Toaster } from "../toaster/index.ts";

export function AppProviders({ children }: { children: ReactNode }) {
  return (
    <SettingsProvider>
      <DataProvider>
        <Toaster />
        <SyncToaster />
        {children}
      </DataProvider>
    </SettingsProvider>
  );
}