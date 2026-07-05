"use client";

import { useSyncExternalStore } from "react";

function subscribe(callback: () => void) {
  window.addEventListener("storage", callback);
  return () => window.removeEventListener("storage", callback);
}

function getSnapshot() {
  return !!localStorage.getItem("token");
}

function getServerSnapshot() {
  return false;
}

/** Reads whether a session token is present, without a setState-in-effect. */
export function useHasToken() {
  return useSyncExternalStore(subscribe, getSnapshot, getServerSnapshot);
}
