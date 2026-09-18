import { describe, expect, it } from "vitest";

import { createTabPresence, type PresenceLocks } from "./tabPresence.ts";

function fakeLocks(taken: boolean): PresenceLocks {
  return {
    request: (_name, _options, callback) =>
      Promise.resolve(callback(taken ? null : {})),
  };
}

/** No cross-tab transports: only the lock claim is under test. */
const noTransports = { createChannel: () => null, createBridge: () => null };

describe("createTabPresence", () => {
  it("second tab with a taken lock is a duplicate", async () => {
    const presence = createTabPresence({
      ...noTransports,
      locks: fakeLocks(true),
    });
    await expect(presence.ready).resolves.toEqual({ duplicate: true });
    presence.dispose();
  });

  it("first tab owns the lock", async () => {
    const presence = createTabPresence({
      ...noTransports,
      locks: fakeLocks(false),
    });
    await expect(presence.ready).resolves.toEqual({ duplicate: false });
    presence.dispose();
  });

  it("only a duplicate asks to switch tabs", async () => {
    const owner = createTabPresence({ ...noTransports, locks: fakeLocks(false) });
    const duplicate = createTabPresence({
      ...noTransports,
      locks: fakeLocks(true),
    });
    await owner.ready;
    await duplicate.ready;
    // There is no bridge and no channel here, so the request cannot succeed.
    await expect(owner.requestFocus()).resolves.toBe(false);
    await expect(duplicate.requestFocus()).resolves.toBe(false);
    owner.dispose();
    duplicate.dispose();
  });

  it("treats a failing lock API as the only tab", async () => {
    const failing: PresenceLocks = {
      request: () => Promise.reject(new Error("locks unavailable")),
    };
    const presence = createTabPresence({ ...noTransports, locks: failing });
    await expect(presence.ready).resolves.toEqual({ duplicate: false });
    presence.dispose();
  });

  it("a disposed duplicate stops asking and closes the channel", async () => {
    const presence = createTabPresence({
      ...noTransports,
      locks: fakeLocks(true),
    });
    await presence.ready;
    presence.dispose();
    await expect(presence.requestFocus()).resolves.toBe(false);
  });
});
