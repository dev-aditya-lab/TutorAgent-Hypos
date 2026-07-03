"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { FormEvent, useState } from "react";
import {
  IconAlert,
  IconBriefcase,
  IconChevronDown,
  IconEye,
  IconEyeOff,
  IconGraduationCap,
  IconLock,
  IconMail,
  IconTarget,
  IconUser,
} from "@/components/icons";
import { API_BASE_URL } from "@/lib/api";

type YearOption = "1st" | "2nd" | "3rd" | "4th";
type GoalOption = "FAANG" | "Startup" | "MS Abroad" | "Govt" | "Freelance";

const YEAR_OPTIONS: { value: YearOption; label: string }[] = [
  { value: "1st", label: "1st Year" },
  { value: "2nd", label: "2nd Year" },
  { value: "3rd", label: "3rd Year" },
  { value: "4th", label: "4th Year" },
];

const GOAL_OPTIONS: { value: GoalOption; label: string }[] = [
  { value: "FAANG", label: "FAANG" },
  { value: "Startup", label: "Startup" },
  { value: "MS Abroad", label: "MS Abroad" },
  { value: "Govt", label: "Government" },
  { value: "Freelance", label: "Freelance" },
];

const inputBase =
  "w-full rounded-lg border border-emerald-200 bg-white py-2.5 pl-10 pr-3 text-sm text-slate-800 placeholder:text-slate-400 outline-none transition focus:border-emerald-500 focus:ring-2 focus:ring-emerald-100";

export default function SignupPage() {
  const router = useRouter();

  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [year, setYear] = useState<YearOption | "">("");
  const [goal, setGoal] = useState<GoalOption | "">("");
  const [targetRole, setTargetRole] = useState("");

  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);

    if (!name || !email || !password || !year || !goal || !targetRole) {
      setError("Please fill in every field to continue.");
      return;
    }

    if (password.length < 8) {
      setError("Password must be at least 8 characters.");
      return;
    }

    setIsSubmitting(true);
    try {
      const response = await fetch(`${API_BASE_URL}/auth/register`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name,
          email,
          password,
          year,
          goal,
          target_role: targetRole,
          current_skills: [],
        }),
      });

      const data = await response.json();

      if (!response.ok) {
        setError(data?.detail ?? "Something went wrong. Please try again.");
        return;
      }

      localStorage.setItem("token", data.token);
      router.push("/roadmap");
    } catch {
      setError("Could not reach the server. Please try again.");
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <main className="flex min-h-screen items-center justify-center bg-emerald-50 px-4 py-12">
      <div className="w-full max-w-md rounded-2xl border border-emerald-100 bg-white p-8 shadow-sm">
        <div className="mb-8 text-center">
          <h1 className="text-2xl font-semibold text-slate-900">Create your account</h1>
          <p className="mt-1 text-sm text-slate-500">
            Tell us a bit about yourself so we can personalize your learning path.
          </p>
        </div>

        {error && (
          <div className="mb-5 flex items-start gap-2 rounded-lg border border-red-200 bg-red-50 px-3 py-2.5 text-sm text-red-700">
            <IconAlert className="mt-0.5 h-4 w-4 shrink-0" />
            <span>{error}</span>
          </div>
        )}

        <form onSubmit={handleSubmit} className="space-y-4" noValidate>
          <div>
            <label htmlFor="name" className="mb-1.5 block text-sm font-medium text-slate-700">
              Full name
            </label>
            <div className="relative">
              <IconUser className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-emerald-500" />
              <input
                id="name"
                type="text"
                autoComplete="name"
                placeholder="Jane Doe"
                className={inputBase}
                value={name}
                onChange={(e) => setName(e.target.value)}
              />
            </div>
          </div>

          <div>
            <label htmlFor="email" className="mb-1.5 block text-sm font-medium text-slate-700">
              Email
            </label>
            <div className="relative">
              <IconMail className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-emerald-500" />
              <input
                id="email"
                type="email"
                autoComplete="email"
                placeholder="jane@example.com"
                className={inputBase}
                value={email}
                onChange={(e) => setEmail(e.target.value)}
              />
            </div>
          </div>

          <div>
            <label htmlFor="password" className="mb-1.5 block text-sm font-medium text-slate-700">
              Password
            </label>
            <div className="relative">
              <IconLock className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-emerald-500" />
              <input
                id="password"
                type={showPassword ? "text" : "password"}
                autoComplete="new-password"
                placeholder="At least 8 characters"
                className={`${inputBase} pr-10`}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
              />
              <button
                type="button"
                onClick={() => setShowPassword((v) => !v)}
                className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400 transition hover:text-emerald-600"
                aria-label={showPassword ? "Hide password" : "Show password"}
              >
                {showPassword ? <IconEyeOff className="h-4 w-4" /> : <IconEye className="h-4 w-4" />}
              </button>
            </div>
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div>
              <label htmlFor="year" className="mb-1.5 block text-sm font-medium text-slate-700">
                Studying year
              </label>
              <div className="relative">
                <IconGraduationCap className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-emerald-500" />
                <select
                  id="year"
                  className={`${inputBase} appearance-none pr-8`}
                  value={year}
                  onChange={(e) => setYear(e.target.value as YearOption)}
                >
                  <option value="" disabled>
                    Select
                  </option>
                  {YEAR_OPTIONS.map((option) => (
                    <option key={option.value} value={option.value}>
                      {option.label}
                    </option>
                  ))}
                </select>
                <IconChevronDown className="pointer-events-none absolute right-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
              </div>
            </div>

            <div>
              <label htmlFor="goal" className="mb-1.5 block text-sm font-medium text-slate-700">
                Goal
              </label>
              <div className="relative">
                <IconTarget className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-emerald-500" />
                <select
                  id="goal"
                  className={`${inputBase} appearance-none pr-8`}
                  value={goal}
                  onChange={(e) => setGoal(e.target.value as GoalOption)}
                >
                  <option value="" disabled>
                    Select
                  </option>
                  {GOAL_OPTIONS.map((option) => (
                    <option key={option.value} value={option.value}>
                      {option.label}
                    </option>
                  ))}
                </select>
                <IconChevronDown className="pointer-events-none absolute right-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
              </div>
            </div>
          </div>

          <div>
            <label htmlFor="targetRole" className="mb-1.5 block text-sm font-medium text-slate-700">
              Target role / field
            </label>
            <div className="relative">
              <IconBriefcase className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-emerald-500" />
              <input
                id="targetRole"
                type="text"
                placeholder="e.g. Backend Engineer"
                className={inputBase}
                value={targetRole}
                onChange={(e) => setTargetRole(e.target.value)}
              />
            </div>
          </div>

          <button
            type="submit"
            disabled={isSubmitting}
            className="mt-2 w-full rounded-lg bg-emerald-600 py-2.5 text-sm font-semibold text-white transition hover:bg-emerald-700 disabled:cursor-not-allowed disabled:opacity-60"
          >
            {isSubmitting ? "Creating account..." : "Create account"}
          </button>
        </form>

        <p className="mt-6 text-center text-sm text-slate-500">
          Already have an account?{" "}
          <Link href="/login" className="font-medium text-emerald-600 hover:text-emerald-700">
            Log in
          </Link>
        </p>
      </div>
    </main>
  );
}
