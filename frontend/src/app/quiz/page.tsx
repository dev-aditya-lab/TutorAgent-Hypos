"use client";

import { useState } from "react";
import { NavBar } from "@/components/NavBar";
import {
  IconAlert,
  IconBookOpen,
  IconCheckCircle,
  IconChevronLeft,
  IconChevronRight,
  IconSpinner,
} from "@/components/icons";
import { authFetch } from "@/lib/api";
import { useAuthGuard } from "@/hooks/useAuthGuard";

type Phase = "idle" | "loading" | "study" | "active" | "submitting" | "done";

type MCQQuestion = { question: string; options: string[]; correct_index: number };

type DailyTask = {
  task_id: string;
  topic: string;
  resource: { title: string; content: string };
  questions: MCQQuestion[];
};

type QuizResult = {
  score: number;
  total: number;
  percentage: number;
  struggled: boolean;
  feedback: string;
};

const MOCK_TASK: DailyTask = {
  task_id: "mock-task",
  topic: "Arrays & Hash Maps",
  resource: {
    title: "Quick refresher: Arrays & Hash Maps",
    content:
      "Arrays give O(1) index access but O(n) search. Hash maps trade extra memory for average O(1) lookup, insert, and delete by hashing keys into buckets. Reach for a hash map whenever you catch yourself scanning a list repeatedly to check membership or count occurrences.",
  },
  questions: [
    {
      question: "What is the average time complexity of a lookup in a hash map?",
      options: ["O(1)", "O(log n)", "O(n)", "O(n^2)"],
      correct_index: 0,
    },
    {
      question: "Which operation is a plain array generally worse at than a hash map?",
      options: ["Index access", "Membership check", "Iteration order", "Contiguous memory access"],
      correct_index: 1,
    },
    {
      question: "What causes hash map performance to degrade toward O(n)?",
      options: [
        "Using too few keys",
        "Sorting the keys",
        "Frequent hash collisions",
        "Storing large values",
      ],
      correct_index: 2,
    },
    {
      question: "Which problem is a textbook fit for a hash map?",
      options: [
        "Finding the two numbers in a list that sum to a target",
        "Finding the median of a sorted array",
        "Reversing a linked list",
        "Binary searching a sorted array",
      ],
      correct_index: 0,
    },
    {
      question: "What's a common trade-off when using a hash map instead of an array?",
      options: [
        "Slower reads",
        "Higher memory usage",
        "No support for deletion",
        "Requires sorted input",
      ],
      correct_index: 1,
    },
  ],
};

export default function QuizPage() {
  const { studentId, ready, handleSessionExpired } = useAuthGuard();

  const [phase, setPhase] = useState<Phase>("idle");
  const [task, setTask] = useState<DailyTask | null>(null);
  const [answers, setAnswers] = useState<number[]>([]);
  const [currentIndex, setCurrentIndex] = useState(0);
  const [result, setResult] = useState<QuizResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [isMock, setIsMock] = useState(false);

  function startMockQuiz() {
    setIsMock(true);
    setNotice("Demo mode — the backend isn't reachable, so this is running on a mock quiz.");
    setTask(MOCK_TASK);
    setAnswers(new Array(MOCK_TASK.questions.length).fill(-1));
    setCurrentIndex(0);
    setPhase("study");
  }

  async function startQuiz() {
    if (!studentId) return;
    setError(null);
    setNotice(null);
    setIsMock(false);
    setPhase("loading");
    try {
      const response = await authFetch(`/tasks/today/${studentId}`);

      if (response.status === 401) {
        handleSessionExpired();
        return;
      }

      const data = await response.json();

      if (!response.ok) {
        setError(data?.detail ?? "Could not load today's task. Please try again.");
        setPhase("idle");
        return;
      }

      setTask(data);
      setAnswers(new Array(data.questions.length).fill(-1));
      setCurrentIndex(0);
      setPhase("study");
    } catch {
      startMockQuiz();
    }
  }

  function selectOption(optionIndex: number) {
    setAnswers((prev) => {
      const next = [...prev];
      next[currentIndex] = optionIndex;
      return next;
    });
  }

  function goNext() {
    if (!task) return;
    setCurrentIndex((i) => Math.min(i + 1, task.questions.length - 1));
  }

  function goBack() {
    setCurrentIndex((i) => Math.max(i - 1, 0));
  }

  async function submitQuiz() {
    if (!task || !studentId) return;
    setError(null);
    setPhase("submitting");

    if (isMock) {
      const total = task.questions.length;
      const score = answers.reduce(
        (acc, answer, i) => acc + (answer === task.questions[i].correct_index ? 1 : 0),
        0
      );
      const percentage = Math.round((score / total) * 100);
      const struggled = percentage < 60;
      window.setTimeout(() => {
        setResult({
          score,
          total,
          percentage,
          struggled,
          feedback: struggled
            ? "You're still building confidence here — revisit the refresher above and try a similar set again soon."
            : "Nice work! You've got a solid handle on this topic — keep this momentum going.",
        });
        setPhase("done");
      }, 500);
      return;
    }

    try {
      const response = await authFetch("/tasks/submit", {
        method: "POST",
        body: JSON.stringify({ student_id: studentId, task_id: task.task_id, answers }),
      });

      if (response.status === 401) {
        handleSessionExpired();
        return;
      }

      const data = await response.json();

      if (!response.ok) {
        setError(data?.detail ?? "Could not submit your answers. Please try again.");
        setPhase("active");
        return;
      }

      setResult(data);
      setPhase("done");
    } catch {
      setError("Could not reach the server. Please try again.");
      setPhase("active");
    }
  }

  function retakeQuiz() {
    setPhase("idle");
    setTask(null);
    setAnswers([]);
    setCurrentIndex(0);
    setResult(null);
    setError(null);
    setNotice(null);
    setIsMock(false);
  }

  const currentQuestion = task?.questions[currentIndex] ?? null;
  const isLastQuestion = task ? currentIndex === task.questions.length - 1 : false;
  const hasAnsweredCurrent = answers[currentIndex] !== undefined && answers[currentIndex] !== -1;

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
      <div className="w-full max-w-2xl rounded-2xl border border-emerald-100 bg-white p-6 shadow-sm sm:p-8">
        <div className="mb-6 text-center">
          <h1 className="text-2xl font-semibold text-slate-900">Daily Quiz</h1>
          <p className="mt-1 text-sm text-slate-500">Read the refresher, then answer one question at a time.</p>
        </div>

        {error && (
          <div className="mb-5 flex items-start gap-2 rounded-lg border border-red-200 bg-red-50 px-3 py-2.5 text-sm text-red-700">
            <IconAlert className="mt-0.5 h-4 w-4 shrink-0" />
            <span>{error}</span>
          </div>
        )}

        {notice && (
          <div className="mb-5 flex items-start gap-2 rounded-lg border border-emerald-200 bg-emerald-50 px-3 py-2.5 text-sm text-emerald-700">
            <IconAlert className="mt-0.5 h-4 w-4 shrink-0" />
            <span>{notice}</span>
          </div>
        )}

        {phase === "idle" && (
          <div className="flex flex-col items-center gap-4 py-10 text-center">
            <p className="max-w-sm text-sm text-slate-500">
              A short refresher followed by a handful of multiple-choice questions on today&apos;s topic.
            </p>
            <button
              type="button"
              onClick={startQuiz}
              className="rounded-lg bg-emerald-600 px-6 py-2.5 text-sm font-semibold text-white transition hover:bg-emerald-700"
            >
              Start quiz
            </button>
          </div>
        )}

        {phase === "loading" && (
          <div className="flex flex-col items-center gap-3 py-10 text-sm text-slate-500">
            <IconSpinner className="h-6 w-6 animate-spin text-emerald-600" />
            Preparing today&apos;s quiz...
          </div>
        )}

        {phase === "study" && task && (
          <div className="flex flex-col gap-4">
            <span className="w-fit rounded-full border border-emerald-200 bg-emerald-50 px-2.5 py-1 text-xs font-medium text-emerald-700">
              {task.topic}
            </span>
            <div className="rounded-lg border border-emerald-100 bg-emerald-50/40 p-4">
              <div className="mb-2 flex items-center gap-2 text-emerald-700">
                <IconBookOpen className="h-4 w-4" />
                <p className="text-sm font-semibold">{task.resource.title}</p>
              </div>
              <p className="text-sm leading-relaxed text-slate-700">{task.resource.content}</p>
            </div>
            <button
              type="button"
              onClick={() => setPhase("active")}
              className="self-center rounded-lg bg-emerald-600 px-6 py-2.5 text-sm font-semibold text-white transition hover:bg-emerald-700"
            >
              Begin {task.questions.length} questions
            </button>
          </div>
        )}

        {phase !== "done" && task && currentQuestion && (phase === "active" || phase === "submitting") && (
          <div className="flex flex-col gap-5">
            <div className="flex items-center justify-between text-xs font-medium text-emerald-700">
              <span>
                Question {currentIndex + 1} of {task.questions.length}
              </span>
              <div className="flex gap-1">
                {task.questions.map((_, i) => (
                  <span
                    key={i}
                    className={`h-1.5 w-5 rounded-full ${
                      i === currentIndex ? "bg-emerald-600" : i < currentIndex ? "bg-emerald-300" : "bg-emerald-100"
                    }`}
                  />
                ))}
              </div>
            </div>

            <p className="text-base font-medium text-slate-900">{currentQuestion.question}</p>

            <div className="flex flex-col gap-2.5">
              {currentQuestion.options.map((option, optionIndex) => {
                const selected = answers[currentIndex] === optionIndex;
                return (
                  <button
                    key={optionIndex}
                    type="button"
                    onClick={() => selectOption(optionIndex)}
                    disabled={phase === "submitting"}
                    className={`flex items-center gap-3 rounded-lg border px-4 py-3 text-left text-sm transition disabled:cursor-not-allowed ${
                      selected
                        ? "border-emerald-500 bg-emerald-50 text-emerald-800"
                        : "border-emerald-200 bg-white text-slate-700 hover:bg-emerald-50/60"
                    }`}
                  >
                    <span
                      className={`flex h-5 w-5 shrink-0 items-center justify-center rounded-full border text-xs ${
                        selected
                          ? "border-emerald-600 bg-emerald-600 text-white"
                          : "border-slate-300 text-transparent"
                      }`}
                    >
                      {String.fromCharCode(65 + optionIndex)}
                    </span>
                    {option}
                  </button>
                );
              })}
            </div>

            <div className="flex items-center justify-between">
              <button
                type="button"
                onClick={goBack}
                disabled={currentIndex === 0 || phase === "submitting"}
                className="flex items-center gap-1 rounded-lg border border-emerald-200 bg-white px-4 py-2 text-sm font-medium text-emerald-700 transition hover:bg-emerald-50 disabled:cursor-not-allowed disabled:opacity-40"
              >
                <IconChevronLeft className="h-4 w-4" />
                Back
              </button>

              {isLastQuestion ? (
                <button
                  type="button"
                  onClick={submitQuiz}
                  disabled={!hasAnsweredCurrent || phase === "submitting"}
                  className="flex items-center gap-1 rounded-lg bg-emerald-600 px-5 py-2 text-sm font-semibold text-white transition hover:bg-emerald-700 disabled:cursor-not-allowed disabled:opacity-50"
                >
                  {phase === "submitting" ? (
                    <>
                      <IconSpinner className="h-4 w-4 animate-spin" />
                      Submitting...
                    </>
                  ) : (
                    "Submit quiz"
                  )}
                </button>
              ) : (
                <button
                  type="button"
                  onClick={goNext}
                  disabled={!hasAnsweredCurrent}
                  className="flex items-center gap-1 rounded-lg bg-emerald-600 px-5 py-2 text-sm font-semibold text-white transition hover:bg-emerald-700 disabled:cursor-not-allowed disabled:opacity-50"
                >
                  Next
                  <IconChevronRight className="h-4 w-4" />
                </button>
              )}
            </div>
          </div>
        )}

        {phase === "done" && result && (
          <div className="flex flex-col gap-4">
            <div className="flex items-center gap-2 rounded-lg border border-emerald-200 bg-emerald-50 px-4 py-3">
              <IconCheckCircle className="h-5 w-5 shrink-0 text-emerald-600" />
              <div>
                <p className="text-sm font-semibold text-slate-900">Quiz complete</p>
                <p className="text-sm text-slate-600">
                  {result.score} / {result.total} correct ({Math.round(result.percentage)}%)
                </p>
              </div>
              {result.struggled && (
                <span className="ml-auto rounded-full border border-amber-200 bg-amber-50 px-2.5 py-1 text-xs font-medium text-amber-700">
                  Needs review
                </span>
              )}
            </div>

            <p className="text-sm leading-relaxed text-slate-700">{result.feedback}</p>

            <button
              type="button"
              onClick={retakeQuiz}
              className="self-center rounded-lg border border-emerald-200 bg-white px-5 py-2 text-sm font-medium text-emerald-700 transition hover:bg-emerald-50"
            >
              Take another quiz
            </button>
          </div>
        )}
      </div>
    </main>
  );
}
