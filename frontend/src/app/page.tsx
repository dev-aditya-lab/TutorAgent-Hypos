"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect } from "react";
import {
  IconBookOpen,
  IconMic,
  IconSpinner,
  IconTarget,
  IconTrendingUp,
} from "@/components/icons";
import { useHasToken } from "@/hooks/useHasToken";

const FEATURES = [
  {
    icon: IconTarget,
    title: "Personalised roadmap",
    description: "A 12-week study plan tailored to your year, goals, and target role.",
  },
  {
    icon: IconBookOpen,
    title: "Daily quizzes",
    description: "A short refresher and a handful of MCQs on today's topic, every day.",
  },
  {
    icon: IconMic,
    title: "AI mock interviews",
    description: "Practice technical interviews out loud and get scored feedback.",
  },
  {
    icon: IconTrendingUp,
    title: "Progress tracking",
    description: "See your strengths, weak spots, and an AI-written learning summary.",
  },
];

export default function HomePage() {
  const router = useRouter();
  const hasToken = useHasToken();

  useEffect(() => {
    if (hasToken) {
      router.replace("/roadmap");
    }
  }, [hasToken, router]);

  if (hasToken) {
    return (
      <main className="flex min-h-screen items-center justify-center bg-emerald-50 px-4 py-12">
        <IconSpinner className="h-6 w-6 animate-spin text-emerald-600" />
      </main>
    );
  }

  return (
    <main className="flex min-h-screen flex-col items-center bg-emerald-50 px-4 py-16">
      <div className="w-full max-w-3xl text-center">
        <span className="mb-4 inline-block rounded-full border border-emerald-200 bg-white px-3 py-1 text-xs font-medium text-emerald-700">
          AI Tutor Agent
        </span>
        <h1 className="text-3xl font-semibold text-slate-900 sm:text-4xl">
          Your personal learning companion
        </h1>
        <p className="mx-auto mt-3 max-w-xl text-sm text-slate-500 sm:text-base">
          A roadmap, daily quizzes, and mock interviews built around your goals — powered by AI
          that remembers what you&apos;ve learned.
        </p>

        <div className="mt-8 flex items-center justify-center gap-3">
          <Link
            href="/signup"
            className="rounded-lg bg-emerald-600 px-6 py-2.5 text-sm font-semibold text-white transition hover:bg-emerald-700"
          >
            Get started
          </Link>
          <Link
            href="/login"
            className="rounded-lg border border-emerald-200 bg-white px-6 py-2.5 text-sm font-semibold text-emerald-700 transition hover:bg-emerald-50"
          >
            Log in
          </Link>
        </div>
      </div>

      <div className="mt-14 grid w-full max-w-3xl grid-cols-1 gap-4 sm:grid-cols-2">
        {FEATURES.map(({ icon: Icon, title, description }) => (
          <div
            key={title}
            className="rounded-2xl border border-emerald-100 bg-white p-5 text-left shadow-sm"
          >
            <div className="mb-2 flex items-center gap-2 text-emerald-700">
              <Icon className="h-5 w-5" />
              <p className="text-sm font-semibold text-slate-900">{title}</p>
            </div>
            <p className="text-sm text-slate-500">{description}</p>
          </div>
        ))}
      </div>
    </main>
  );
}
