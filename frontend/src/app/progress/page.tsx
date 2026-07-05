"use client";

import { useEffect, useState } from "react";
import { NavBar } from "@/components/NavBar";
import { IconAlert, IconBrain, IconSpinner, IconTrendingUp } from "@/components/icons";
import { authFetch } from "@/lib/api";
import { useAuthGuard } from "@/hooks/useAuthGuard";

type TopicProgress = {
  topic: string;
  attempts: number;
  best_score: number;
  last_attempted: string;
  weak: boolean;
};

type ProgressData = {
  student_id: string;
  topics: TopicProgress[];
  memory_summary: string;
};

type Phase = "loading" | "ready" | "error";

type ProgressResult =
  | { kind: "unauthorized" }
  | { kind: "ok"; data: ProgressData }
  | { kind: "error"; message: string };

// Pure fetch helper — no component state/setters referenced, so it is safe
// to call directly from the mount effect below.
async function fetchProgress(id: string): Promise<ProgressResult> {
  try {
    const response = await authFetch(`/progress/${id}`);
    if (response.status === 401) return { kind: "unauthorized" };

    const data = await response.json();
    if (!response.ok) {
      return { kind: "error", message: data?.detail ?? "Could not load your progress. Please try again." };
    }
    return { kind: "ok", data };
  } catch {
    return {
      kind: "error",
      message: "Could not reach the server. Make sure the backend is running and try again.",
    };
  }
}

export default function ProgressPage() {
  const { studentId, ready, handleSessionExpired } = useAuthGuard();

  const [phase, setPhase] = useState<Phase>("loading");
  const [progress, setProgress] = useState<ProgressData | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!ready || !studentId) return;
    let cancelled = false;

    fetchProgress(studentId).then((result) => {
      if (cancelled) return;
      if (result.kind === "unauthorized") {
        handleSessionExpired();
      } else if (result.kind === "error") {
        setError(result.message);
        setPhase("error");
      } else {
        setProgress(result.data);
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
    fetchProgress(studentId).then((result) => {
      if (result.kind === "unauthorized") {
        handleSessionExpired();
      } else if (result.kind === "error") {
        setError(result.message);
        setPhase("error");
      } else {
        setProgress(result.data);
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
        <div className="mb-6">
          <h1 className="text-2xl font-semibold text-slate-900">Your Progress</h1>
          <p className="mt-1 text-sm text-slate-500">
            Topic-by-topic performance, plus an AI summary of your learning journey.
          </p>
        </div>

        {phase === "loading" && (
          <div className="flex flex-col items-center gap-3 py-16 text-sm text-slate-500">
            <IconSpinner className="h-6 w-6 animate-spin text-emerald-600" />
            Loading your progress...
          </div>
        )}

        {phase === "error" && (
          <div className="flex flex-col gap-4">
            <div className="flex items-start gap-2 rounded-lg border border-red-200 bg-red-50 px-3 py-2.5 text-sm text-red-700">
              <IconAlert className="mt-0.5 h-4 w-4 shrink-0" />
              <span>{error}</span>
            </div>
            <button
              type="button"
              onClick={retryLoad}
              className="self-center rounded-lg bg-emerald-600 px-6 py-2.5 text-sm font-semibold text-white transition hover:bg-emerald-700"
            >
              Retry
            </button>
          </div>
        )}

        {phase === "ready" && progress && (
          <div className="flex flex-col gap-6">
            <div className="rounded-lg border border-emerald-100 bg-emerald-50/40 p-4">
              <div className="mb-2 flex items-center gap-2 text-emerald-700">
                <IconBrain className="h-4 w-4" />
                <p className="text-sm font-semibold">Learning journey summary</p>
              </div>
              <p className="text-sm leading-relaxed text-slate-700">{progress.memory_summary}</p>
            </div>

            <div>
              <div className="mb-3 flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-slate-500">
                <IconTrendingUp className="h-3.5 w-3.5" />
                Topics
              </div>

              {progress.topics.length === 0 ? (
                <p className="text-sm text-slate-500">
                  No quiz attempts yet. Complete a daily quiz to start building your progress history.
                </p>
              ) : (
                <div className="flex flex-col gap-2.5">
                  {progress.topics.map((topic) => (
                    <div
                      key={topic.topic}
                      className="flex items-center justify-between gap-3 rounded-lg border border-emerald-100 bg-white p-3"
                    >
                      <div>
                        <p className="text-sm font-medium text-slate-900">{topic.topic}</p>
                        <p className="text-xs text-slate-500">
                          {topic.attempts} attempt{topic.attempts === 1 ? "" : "s"} · best{" "}
                          {topic.best_score}% · last{" "}
                          {new Date(topic.last_attempted).toLocaleDateString()}
                        </p>
                      </div>
                      {topic.weak ? (
                        <span className="shrink-0 rounded-full border border-amber-200 bg-amber-50 px-2.5 py-1 text-xs font-medium text-amber-700">
                          Needs review
                        </span>
                      ) : (
                        <span className="shrink-0 rounded-full border border-emerald-200 bg-emerald-50 px-2.5 py-1 text-xs font-medium text-emerald-700">
                          Solid
                        </span>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        )}
      </div>
    </main>
  );
}
