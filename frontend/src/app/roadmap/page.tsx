"use client";

import { useEffect, useState } from "react";
import { NavBar } from "@/components/NavBar";
import {
  IconAlert,
  IconCalendar,
  IconRefresh,
  IconSpinner,
  IconTarget,
} from "@/components/icons";
import { authFetch } from "@/lib/api";
import { useAuthGuard } from "@/hooks/useAuthGuard";

type WeekPlan = { week: number; focus: string; topics: string[] };

type Roadmap = {
  student_id: string;
  weeks: WeekPlan[];
  generated_at: string;
};

type Phase = "loading" | "empty" | "ready" | "generating" | "error";

type RoadmapResult =
  | { kind: "unauthorized" }
  | { kind: "empty" }
  | { kind: "ok"; data: Roadmap }
  | { kind: "error"; message: string };

// Pure fetch helpers — no references to component state/setters, so they can
// be called directly from an effect without tripping the "no setState in
// effect" check. State updates only happen in the `.then()` callbacks below.
async function fetchRoadmap(id: string): Promise<RoadmapResult> {
  try {
    const response = await authFetch(`/roadmap/${id}`);
    if (response.status === 401) return { kind: "unauthorized" };
    if (response.status === 404) return { kind: "empty" };

    const data = await response.json();
    if (!response.ok) {
      return { kind: "error", message: data?.detail ?? "Could not load your roadmap. Please try again." };
    }
    return { kind: "ok", data };
  } catch {
    return {
      kind: "error",
      message: "Could not reach the server. Make sure the backend is running and try again.",
    };
  }
}

async function requestRoadmapGeneration(): Promise<RoadmapResult> {
  try {
    const response = await authFetch("/roadmap/generate", { method: "POST" });
    if (response.status === 401) return { kind: "unauthorized" };

    const data = await response.json();
    if (!response.ok) {
      return {
        kind: "error",
        message: data?.detail ?? "Could not generate your roadmap. Please try again.",
      };
    }
    return { kind: "ok", data };
  } catch {
    return {
      kind: "error",
      message: "Could not reach the server. Make sure the backend is running and try again.",
    };
  }
}

export default function RoadmapPage() {
  const { studentId, ready, handleSessionExpired } = useAuthGuard();

  const [phase, setPhase] = useState<Phase>("loading");
  const [roadmap, setRoadmap] = useState<Roadmap | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!ready || !studentId) return;
    let cancelled = false;

    fetchRoadmap(studentId).then((result) => {
      if (cancelled) return;
      if (result.kind === "unauthorized") {
        handleSessionExpired();
      } else if (result.kind === "empty") {
        setRoadmap(null);
        setPhase("empty");
      } else if (result.kind === "error") {
        setError(result.message);
        setPhase("error");
      } else {
        setRoadmap(result.data);
        setPhase("ready");
      }
    });

    return () => {
      cancelled = true;
    };
  }, [ready, studentId, handleSessionExpired]);

  function retryLoad() {
    if (!studentId) return;
    setPhase("loading");
    setError(null);
    fetchRoadmap(studentId).then((result) => {
      if (result.kind === "unauthorized") {
        handleSessionExpired();
      } else if (result.kind === "empty") {
        setRoadmap(null);
        setPhase("empty");
      } else if (result.kind === "error") {
        setError(result.message);
        setPhase("error");
      } else {
        setRoadmap(result.data);
        setPhase("ready");
      }
    });
  }

  function generateRoadmap() {
    setPhase("generating");
    setError(null);
    requestRoadmapGeneration().then((result) => {
      if (result.kind === "unauthorized") {
        handleSessionExpired();
      } else if (result.kind === "error") {
        setError(result.message);
        setPhase(roadmap ? "ready" : "empty");
      } else if (result.kind === "ok") {
        setRoadmap(result.data);
        setPhase("ready");
      }
    });
  }

  if (!ready) {
    return (
      <main className="flex min-h-screen items-center justify-center bg-emerald-50 px-4 py-12">
        <IconSpinner className="h-6 w-6 animate-spin text-emerald-600" />
      </main>
    );
  }

  return (
    <main className="flex min-h-screen flex-col items-center bg-emerald-50 px-4 py-10">
      <NavBar />

      <div className="w-full max-w-3xl rounded-2xl border border-emerald-100 bg-white p-6 shadow-sm sm:p-8">
        <div className="mb-6 flex flex-wrap items-start justify-between gap-3">
          <div>
            <h1 className="text-2xl font-semibold text-slate-900">Your Roadmap</h1>
            <p className="mt-1 text-sm text-slate-500">
              A personalised 12-week study plan generated for your goals.
            </p>
          </div>
          {phase === "ready" && roadmap && (
            <button
              type="button"
              onClick={generateRoadmap}
              className="flex items-center gap-1.5 rounded-lg border border-emerald-200 bg-white px-4 py-2 text-sm font-medium text-emerald-700 transition hover:bg-emerald-50"
            >
              <IconRefresh className="h-4 w-4" />
              Regenerate
            </button>
          )}
        </div>

        {error && (
          <div className="mb-5 flex items-start gap-2 rounded-lg border border-red-200 bg-red-50 px-3 py-2.5 text-sm text-red-700">
            <IconAlert className="mt-0.5 h-4 w-4 shrink-0" />
            <span>{error}</span>
          </div>
        )}

        {phase === "loading" && (
          <div className="flex flex-col items-center gap-3 py-16 text-sm text-slate-500">
            <IconSpinner className="h-6 w-6 animate-spin text-emerald-600" />
            Loading your roadmap...
          </div>
        )}

        {phase === "empty" && (
          <div className="flex flex-col items-center gap-4 py-16 text-center">
            <p className="max-w-sm text-sm text-slate-500">
              You don&apos;t have a roadmap yet. Generate a personalised 12-week plan based on your
              goals, year, and current skills.
            </p>
            <button
              type="button"
              onClick={generateRoadmap}
              className="rounded-lg bg-emerald-600 px-6 py-2.5 text-sm font-semibold text-white transition hover:bg-emerald-700"
            >
              Generate my roadmap
            </button>
          </div>
        )}

        {phase === "generating" && (
          <div className="flex flex-col items-center gap-3 py-16 text-sm text-slate-500">
            <IconSpinner className="h-6 w-6 animate-spin text-emerald-600" />
            Generating your personalised roadmap... this can take a moment.
          </div>
        )}

        {phase === "error" && !roadmap && (
          <div className="flex flex-col items-center gap-4 py-10 text-center">
            <button
              type="button"
              onClick={retryLoad}
              className="rounded-lg bg-emerald-600 px-6 py-2.5 text-sm font-semibold text-white transition hover:bg-emerald-700"
            >
              Retry
            </button>
          </div>
        )}

        {roadmap && (phase === "ready" || phase === "error") && (
          <div className="flex flex-col gap-4">
            <div className="flex items-center gap-1.5 text-xs text-slate-400">
              <IconCalendar className="h-3.5 w-3.5" />
              Generated {new Date(roadmap.generated_at).toLocaleDateString(undefined, {
                year: "numeric",
                month: "long",
                day: "numeric",
              })}
            </div>

            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
              {roadmap.weeks
                .slice()
                .sort((a, b) => a.week - b.week)
                .map((week) => (
                  <div
                    key={week.week}
                    className="rounded-lg border border-emerald-100 bg-emerald-50/40 p-4"
                  >
                    <div className="mb-2 flex items-center gap-2">
                      <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-emerald-600 text-xs font-semibold text-white">
                        {week.week}
                      </span>
                      <div className="flex items-center gap-1.5 text-emerald-700">
                        <IconTarget className="h-4 w-4" />
                        <p className="text-sm font-semibold">{week.focus}</p>
                      </div>
                    </div>
                    <div className="flex flex-wrap gap-1.5">
                      {week.topics.map((topic) => (
                        <span
                          key={topic}
                          className="rounded-full border border-emerald-200 bg-white px-2.5 py-1 text-xs text-slate-700"
                        >
                          {topic}
                        </span>
                      ))}
                    </div>
                  </div>
                ))}
            </div>
          </div>
        )}
      </div>
    </main>
  );
}
