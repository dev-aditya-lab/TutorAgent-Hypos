"use client";

import { useEffect, useSyncExternalStore } from "react";
import { useRouter } from "next/navigation";
import { getCurrentStudentId, logout } from "@/lib/api";

function subscribe(callback: () => void) {
  window.addEventListener("storage", callback);
  return () => window.removeEventListener("storage", callback);
}

function getServerSnapshot() {
  return null;
}

/**
 * Redirects to /login when there is no valid session, otherwise exposes the
 * authenticated student's id. `ready` is derived straight from the token
 * (via useSyncExternalStore), so there is no setState-in-effect involved.
 */
export function useAuthGuard() {
  const router = useRouter();
  const studentId = useSyncExternalStore(subscribe, getCurrentStudentId, getServerSnapshot);
  const ready = studentId !== null;

  useEffect(() => {
    if (studentId === null) {
      logout();
      router.replace("/login");
    }
  }, [studentId, router]);

  /** Call when an API response comes back 401 (expired/invalid token). */
  function handleSessionExpired() {
    logout();
    router.replace("/login");
  }

  return { studentId, ready, handleSessionExpired };
}
