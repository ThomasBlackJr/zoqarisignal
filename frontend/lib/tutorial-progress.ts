"use client";
import { useSyncExternalStore } from "react";
import type { Account } from "./api";
import { useHydrated } from "./use-hydrated";

export const tutorialStepCount = 4;
type Progress = { step: number; status: "active" | "completed" | "dismissed" };
const initial: Progress = { step: 0, status: "active" };
const changed = "signal-tutorial-change";
// Keep the tutorial usable when browser storage is unavailable.
const memory = new Map<string, string>();
function read(key: string) {
  try {
    return window.localStorage.getItem(key) ?? memory.get(key) ?? null;
  } catch {
    return memory.get(key) ?? null;
  }
}
function subscribe(notify: () => void) {
  window.addEventListener("storage", notify);
  window.addEventListener(changed, notify);
  return () => {
    window.removeEventListener("storage", notify);
    window.removeEventListener(changed, notify);
  };
}
function parse(raw: string | null): Progress {
  try {
    const value = raw ? JSON.parse(raw) : null;
    if (
      value &&
      Number.isInteger(value.step) &&
      value.step >= 0 &&
      value.step < tutorialStepCount &&
      ["active", "completed", "dismissed"].includes(value.status)
    )
      return value;
  } catch {
    /* Invalid browser state starts a fresh tutorial. */
  }
  return initial;
}
export function useTutorialProgress(
  user: Pick<Account, "id" | "organization_id" | "onboarding_completed"> | null,
) {
  const key = `signal:tutorial:v1:${user?.id ?? ""}:${user?.organization_id ?? "personal"}`;
  const raw = useSyncExternalStore(
    subscribe,
    () => read(key),
    () => null,
  );
  const ready = useHydrated();
  const progress = parse(raw);
  function save(next: Progress) {
    const serialized = JSON.stringify(next);
    try {
      window.localStorage.setItem(key, serialized);
      memory.delete(key);
    } catch {
      memory.set(key, serialized);
    }
    window.dispatchEvent(new Event(changed));
  }
  return {
    ...progress,
    ready,
    done: Boolean(user?.onboarding_completed) || progress.status !== "active",
    save,
  };
}
