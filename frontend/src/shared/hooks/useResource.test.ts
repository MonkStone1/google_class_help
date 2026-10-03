import { act, renderHook, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { invalidateAllResources, useResource } from "./useResource.ts";

describe("useResource", () => {
  beforeEach(() => {
    invalidateAllResources();
  });

  it("loads through the fetcher and exposes data + updatedAt", async () => {
    const fetcher = vi.fn().mockResolvedValue("A");
    const { result } = renderHook(() => useResource("a", fetcher));

    expect(result.current.loading).toBe(true);
    await waitFor(() => expect(result.current.data).toBe("A"));
    expect(result.current.loading).toBe(false);
    expect(result.current.updatedAt).not.toBeNull();
    expect(fetcher).toHaveBeenCalledTimes(1);
  });

  it("serves a fresh cached value without refetching", async () => {
    const first = vi.fn().mockResolvedValue("A");
    const { result, unmount } = renderHook(() => useResource("a", first));
    await waitFor(() => expect(result.current.data).toBe("A"));
    unmount();

    const second = vi.fn().mockResolvedValue("A2");
    const { result: again } = renderHook(() => useResource("a", second));
    await waitFor(() => expect(again.current.data).toBe("A"));
    expect(second).not.toHaveBeenCalled();
  });

  it("never shows the previous key's data under the new key", async () => {
    let resolveB: (value: string) => void = () => {};
    const fetcherA = () => Promise.resolve("A");
    const fetcherB = () =>
      new Promise<string>((resolve) => {
        resolveB = resolve;
      });
    const { result, rerender } = renderHook(
      ({ key }: { key: string }) =>
        useResource(key, key === "a" ? fetcherA : fetcherB),
      { initialProps: { key: "a" } },
    );
    await waitFor(() => expect(result.current.data).toBe("A"));

    rerender({ key: "b" });
    // The reset happens during render, before the new request can resolve.
    expect(result.current.data).toBeNull();

    await act(async () => {
      resolveB("B");
    });
    expect(result.current.data).toBe("B");
  });

  it("ignores a response that lands after the key changed", async () => {
    let resolveA: (value: string) => void = () => {};
    const fetcherA = () =>
      new Promise<string>((resolve) => {
        resolveA = resolve;
      });
    const fetcherB = () => Promise.resolve("B");
    const { result, rerender } = renderHook(
      ({ key }: { key: string }) =>
        useResource(key, key === "a" ? fetcherA : fetcherB),
      { initialProps: { key: "a" } },
    );

    rerender({ key: "b" });
    await waitFor(() => expect(result.current.data).toBe("B"));

    await act(async () => {
      resolveA("A");
    });
    expect(result.current.data).toBe("B");
  });

  it("surfaces fetcher errors", async () => {
    const fetcher = vi.fn().mockRejectedValue(new Error("boom"));
    const { result } = renderHook(() => useResource("broken", fetcher));

    await waitFor(() => expect(result.current.error).toBe("boom"));
    expect(result.current.loading).toBe(false);
    expect(result.current.data).toBeNull();
  });

  it("refresh() forces a network read despite a fresh cache", async () => {
    const fetcher = vi
      .fn()
      .mockResolvedValueOnce("first")
      .mockResolvedValueOnce("second");
    const { result } = renderHook(() => useResource("a", fetcher));
    await waitFor(() => expect(result.current.data).toBe("first"));

    act(() => result.current.refresh());
    await waitFor(() => expect(result.current.data).toBe("second"));
    expect(fetcher).toHaveBeenCalledTimes(2);
  });

  it("deduplicates two hooks on the same key into one request", async () => {
    const fetcher = vi.fn().mockResolvedValue("A");
    const first = renderHook(() => useResource("shared", fetcher));
    const second = renderHook(() => useResource("shared", fetcher));

    await waitFor(() => expect(first.result.current.data).toBe("A"));
    await waitFor(() => expect(second.result.current.data).toBe("A"));
    expect(fetcher).toHaveBeenCalledTimes(1);
  });

  it("aborts the request when the last consumer unmounts", async () => {
    const signals: AbortSignal[] = [];
    const fetcher = (signal: AbortSignal) => {
      signals.push(signal);
      return new Promise<string>(() => {}); // never resolves on its own
    };
    const { result, unmount } = renderHook(() =>
      useResource("abort", fetcher),
    );
    await waitFor(() => expect(signals).toHaveLength(1));
    expect(result.current.loading).toBe(true);

    unmount();
    expect(signals[0].aborted).toBe(true);
  });

  it("keeps the request alive while another consumer still needs it", async () => {
    const signals: AbortSignal[] = [];
    const fetcher = (signal: AbortSignal) => {
      signals.push(signal);
      return new Promise<string>(() => {});
    };
    const first = renderHook(() => useResource("shared2", fetcher));
    const second = renderHook(() => useResource("shared2", fetcher));
    await waitFor(() => expect(signals).toHaveLength(1));

    first.unmount();
    expect(signals[0].aborted).toBe(false); // second still holds it

    second.unmount();
    expect(signals[0].aborted).toBe(true);
  });

  it("does not report an error when the request is superseded by a refresh", async () => {
    let resolveFirst: (value: string) => void = () => {};
    const fetcher = vi
      .fn<(signal: AbortSignal) => Promise<string>>()
      .mockImplementationOnce(
        () =>
          new Promise<string>((resolve) => {
            resolveFirst = resolve;
          }),
      )
      .mockResolvedValueOnce("second");
    const { result } = renderHook(() => useResource("race", fetcher));
    await waitFor(() => expect(fetcher).toHaveBeenCalledTimes(1));

    act(() => result.current.refresh());
    await waitFor(() => expect(result.current.data).toBe("second"));

    // The stale response lands after the refresh already replaced it.
    await act(async () => {
      resolveFirst("stale");
    });
    expect(result.current.data).toBe("second");
    expect(result.current.error).toBeNull();
  });
});
