"use client";
import { useEffect, useState } from "react";
import { api } from "./api";
export function useResource<T>(path: string | null, revision = 0) {
  const [result, setResult] = useState<{
    path: string;
    revision: number;
    data?: T;
    error?: string;
  }>();
  useEffect(() => {
    if (!path) return;
    let active = true;
    api<T>(path)
      .then((data) => {
        if (active) setResult({ path, revision, data });
      })
      .catch((e) => {
        if (active) setResult({ path, revision, error: e.message });
      });
    return () => {
      active = false;
    };
  }, [path, revision]);
  return result?.path === path && result.revision === revision
    ? result
    : { data: undefined, error: undefined };
}
