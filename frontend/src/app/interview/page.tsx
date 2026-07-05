"use client";

import { useEffect, useRef, useState } from "react";
import { NavBar } from "@/components/NavBar";
import {
  IconAlert,
  IconCheckCircle,
  IconMic,
  IconSend,
  IconSpinner,
  IconVolume,
} from "@/components/icons";
import { authFetch } from "@/lib/api";
import { useAuthGuard } from "@/hooks/useAuthGuard";

type Role = "assistant" | "user";
type Message = { role: Role; content: string };

type Phase = "idle" | "starting" | "active" | "submitting" | "ending" | "done" | "error";

type PerQuestionEval = { question: string; verdict: string; score: number };

type InterviewEvaluation = {
  score: number;
  strong_topics: string[];
  weak_topics: string[];
  feedback: string;
  per_question: PerQuestionEval[];
};

const TOTAL_QUESTIONS = 6;

const MOCK_QUESTIONS = [
  "Tell me about a project you're proud of and the biggest technical challenge in it.",
  "What's the difference between an array and a linked list, and when would you pick one over the other?",
  "How would you design a URL shortener at a high level?",
  "What's the time complexity of binary search, and why does it work?",
  "Tell me about a time you disagreed with a teammate on a technical decision. How did you resolve it?",
  "Where do you want to be technically a year from now, and what are you doing to get there?",
];

const MOCK_EVALUATION: InterviewEvaluation = {
  score: 78,
  strong_topics: ["Data Structures", "Communication"],
  weak_topics: ["System Design"],
  feedback:
    "Solid fundamentals and clear communication throughout. Spend more time practicing system design trade-offs — scalability and bottlenecks came up but weren't explored in depth.",
  per_question: MOCK_QUESTIONS.map((question) => ({
    question,
    verdict: "Clear answer with reasonable depth; could go further on trade-offs.",
    score: 7,
  })),
};

function speak(text: string, onStart: () => void, onEnd: () => void) {
  if (typeof window === "undefined" || !("speechSynthesis" in window)) {
    onEnd();
    return;
  }
  window.speechSynthesis.cancel();
  const utterance = new SpeechSynthesisUtterance(text);
  utterance.rate = 1;
  utterance.pitch = 1;
  utterance.onstart = onStart;
  utterance.onend = onEnd;
  utterance.onerror = onEnd;
  window.speechSynthesis.speak(utterance);
}

export default function InterviewPage() {
  const { studentId, ready, handleSessionExpired } = useAuthGuard();

  const [phase, setPhase] = useState<Phase>("idle");
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [questionNumber, setQuestionNumber] = useState(1);
  const [transcript, setTranscript] = useState<Message[]>([]);
  const [draftAnswer, setDraftAnswer] = useState("");
  const [isListening, setIsListening] = useState(false);
  const [isSpeaking, setIsSpeaking] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [evaluation, setEvaluation] = useState<InterviewEvaluation | null>(null);
  const [isMock, setIsMock] = useState(false);
  const [mockIndex, setMockIndex] = useState(0);

  const recognitionRef = useRef<SpeechRecognition | null>(null);
  const baseAnswerRef = useRef("");
  const transcriptEndRef = useRef<HTMLDivElement | null>(null);
  const speechSupported =
    typeof window !== "undefined" && !!(window.SpeechRecognition ?? window.webkitSpeechRecognition);

  useEffect(() => {
    transcriptEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [transcript]);

  useEffect(() => {
    return () => {
      recognitionRef.current?.stop();
      if (typeof window !== "undefined" && "speechSynthesis" in window) {
        window.speechSynthesis.cancel();
      }
    };
  }, []);

  function startListening() {
    const SpeechRecognitionCtor = window.SpeechRecognition ?? window.webkitSpeechRecognition;
    if (!SpeechRecognitionCtor) {
      setError("Speech recognition isn't supported in this browser. You can type your answer instead.");
      return;
    }

    baseAnswerRef.current = draftAnswer ? `${draftAnswer} ` : "";
    const recognition = new SpeechRecognitionCtor();
    recognition.lang = "en-US";
    recognition.interimResults = true;
    recognition.continuous = false;
    recognition.maxAlternatives = 1;

    recognition.onresult = (event) => {
      let combined = "";
      for (let i = 0; i < event.results.length; i++) {
        combined += event.results[i][0].transcript;
      }
      setDraftAnswer(baseAnswerRef.current + combined);
    };
    recognition.onerror = () => setIsListening(false);
    recognition.onend = () => setIsListening(false);

    recognitionRef.current = recognition;
    recognition.start();
    setIsListening(true);
  }

  function stopListening() {
    recognitionRef.current?.stop();
    setIsListening(false);
  }

  function startMockInterview() {
    setIsMock(true);
    setNotice("Demo mode — the backend isn't reachable, so this is running on mock interview questions.");
    setSessionId("mock-session");
    setQuestionNumber(1);
    setMockIndex(0);
    setTranscript([{ role: "assistant", content: MOCK_QUESTIONS[0] }]);
    setPhase("active");
    speak(MOCK_QUESTIONS[0], () => setIsSpeaking(true), () => setIsSpeaking(false));
  }

  function submitMockAnswer() {
    const nextIndex = mockIndex + 1;
    window.setTimeout(() => {
      if (nextIndex >= MOCK_QUESTIONS.length) {
        setQuestionNumber(nextIndex + 1);
        finishMockInterview();
        return;
      }
      setMockIndex(nextIndex);
      setQuestionNumber(nextIndex + 1);
      setTranscript((prev) => [...prev, { role: "assistant", content: MOCK_QUESTIONS[nextIndex] }]);
      setPhase("active");
      speak(MOCK_QUESTIONS[nextIndex], () => setIsSpeaking(true), () => setIsSpeaking(false));
    }, 600);
  }

  function finishMockInterview() {
    setPhase("ending");
    window.setTimeout(() => {
      setEvaluation(MOCK_EVALUATION);
      setPhase("done");
    }, 800);
  }

  async function startInterview() {
    if (!studentId) return;
    setError(null);
    setNotice(null);
    setIsMock(false);
    setPhase("starting");
    try {
      const response = await authFetch("/interview/start", {
        method: "POST",
        body: JSON.stringify({ student_id: studentId }),
      });

      if (response.status === 401) {
        handleSessionExpired();
        return;
      }

      const data = await response.json();

      if (!response.ok) {
        setError(data?.detail ?? "Could not start the interview. Please try again.");
        setPhase("idle");
        return;
      }

      setSessionId(data.session_id);
      setQuestionNumber(data.question_number);
      setTranscript([{ role: "assistant", content: data.first_question }]);
      setPhase("active");
      speak(data.first_question, () => setIsSpeaking(true), () => setIsSpeaking(false));
    } catch {
      startMockInterview();
    }
  }

  async function finishInterview(finalSessionId: string) {
    if (!studentId) return;
    setPhase("ending");
    try {
      const response = await authFetch("/interview/end", {
        method: "POST",
        body: JSON.stringify({ session_id: finalSessionId, student_id: studentId }),
      });

      if (response.status === 401) {
        handleSessionExpired();
        return;
      }

      const data = await response.json();

      if (!response.ok) {
        setError(data?.detail ?? "Could not generate your evaluation.");
        setPhase("active");
        return;
      }

      setEvaluation(data);
      setPhase("done");
    } catch {
      setError("Could not reach the server. Please try again.");
      setPhase("active");
    }
  }

  async function submitAnswer() {
    const answer = draftAnswer.trim();
    if (!answer || !sessionId || !studentId) return;

    stopListening();
    setError(null);
    setPhase("submitting");
    setTranscript((prev) => [...prev, { role: "user", content: answer }]);
    setDraftAnswer("");

    if (isMock) {
      submitMockAnswer();
      return;
    }

    try {
      const response = await authFetch("/interview/respond", {
        method: "POST",
        body: JSON.stringify({ session_id: sessionId, student_id: studentId, answer }),
      });

      if (response.status === 401) {
        handleSessionExpired();
        return;
      }

      const data = await response.json();

      if (!response.ok) {
        setError(data?.detail ?? "Something went wrong. Please try again.");
        setPhase("active");
        return;
      }

      setQuestionNumber(data.question_number);

      if (data.done) {
        await finishInterview(sessionId);
        return;
      }

      setTranscript((prev) => [...prev, { role: "assistant", content: data.question }]);
      setPhase("active");
      speak(data.question, () => setIsSpeaking(true), () => setIsSpeaking(false));
    } catch {
      setError("Could not reach the server. Please try again.");
      setPhase("active");
    }
  }

  const isBusy = phase === "starting" || phase === "submitting" || phase === "ending";

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
          <h1 className="text-2xl font-semibold text-slate-900">AI Mock Interview</h1>
          <p className="mt-1 text-sm text-slate-500">
            The interviewer asks a question out loud — answer by voice or by typing.
          </p>
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
              You&apos;ll get {TOTAL_QUESTIONS} questions tailored to your profile. Ready when you are.
            </p>
            <button
              type="button"
              onClick={startInterview}
              className="rounded-lg bg-emerald-600 px-6 py-2.5 text-sm font-semibold text-white transition hover:bg-emerald-700"
            >
              Start interview
            </button>
          </div>
        )}

        {phase === "starting" && (
          <div className="flex flex-col items-center gap-3 py-10 text-sm text-slate-500">
            <IconSpinner className="h-6 w-6 animate-spin text-emerald-600" />
            Preparing your first question...
          </div>
        )}

        {(phase === "active" || phase === "submitting" || phase === "ending" || phase === "done") && (
          <div className="flex flex-col">
            {phase !== "done" && (
              <div className="mb-3 flex items-center justify-between text-xs font-medium text-emerald-700">
                <span>
                  Question {Math.min(questionNumber, TOTAL_QUESTIONS)} of {TOTAL_QUESTIONS}
                </span>
                {isSpeaking && (
                  <span className="flex items-center gap-1 text-emerald-600">
                    <IconVolume className="h-3.5 w-3.5" />
                    Interviewer speaking...
                  </span>
                )}
              </div>
            )}

            <div className="mb-4 flex h-96 flex-col gap-3 overflow-y-auto rounded-lg border border-emerald-100 bg-emerald-50/40 p-4">
              {transcript.map((message, index) => (
                <div
                  key={index}
                  className={`flex ${message.role === "user" ? "justify-end" : "justify-start"}`}
                >
                  <div
                    className={`max-w-[80%] rounded-xl px-3.5 py-2 text-sm leading-relaxed ${
                      message.role === "user"
                        ? "bg-emerald-600 text-white"
                        : "border border-emerald-200 bg-white text-slate-800"
                    }`}
                  >
                    {message.content}
                  </div>
                </div>
              ))}
              {phase === "ending" && (
                <div className="flex items-center gap-2 self-start rounded-xl border border-emerald-200 bg-white px-3.5 py-2 text-sm text-slate-500">
                  <IconSpinner className="h-4 w-4 animate-spin text-emerald-600" />
                  Scoring your interview...
                </div>
              )}
              <div ref={transcriptEndRef} />
            </div>

            {phase !== "done" && (
              <div className="flex items-end gap-2">
                <button
                  type="button"
                  onClick={isListening ? stopListening : startListening}
                  disabled={isBusy || !speechSupported}
                  aria-label={isListening ? "Stop recording" : "Record your answer"}
                  title={speechSupported ? undefined : "Speech recognition isn't supported in this browser"}
                  className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-lg border transition disabled:cursor-not-allowed disabled:opacity-50 ${
                    isListening
                      ? "border-red-300 bg-red-50 text-red-600"
                      : "border-emerald-200 bg-white text-emerald-600 hover:bg-emerald-50"
                  }`}
                >
                  <IconMic className={`h-4 w-4 ${isListening ? "animate-pulse" : ""}`} />
                </button>

                <textarea
                  rows={1}
                  placeholder={isListening ? "Listening..." : "Type or record your answer"}
                  className="max-h-32 flex-1 resize-none rounded-lg border border-emerald-200 bg-white px-3 py-2.5 text-sm text-slate-800 placeholder:text-slate-400 outline-none transition focus:border-emerald-500 focus:ring-2 focus:ring-emerald-100"
                  value={draftAnswer}
                  onChange={(e) => setDraftAnswer(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" && !e.shiftKey) {
                      e.preventDefault();
                      submitAnswer();
                    }
                  }}
                  disabled={isBusy}
                />

                <button
                  type="button"
                  onClick={submitAnswer}
                  disabled={isBusy || !draftAnswer.trim()}
                  aria-label="Send answer"
                  className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-emerald-600 text-white transition hover:bg-emerald-700 disabled:cursor-not-allowed disabled:opacity-50"
                >
                  {phase === "submitting" ? (
                    <IconSpinner className="h-4 w-4 animate-spin" />
                  ) : (
                    <IconSend className="h-4 w-4" />
                  )}
                </button>
              </div>
            )}
          </div>
        )}

        {phase === "done" && evaluation && (
          <div className="flex flex-col gap-4">
            <div className="flex items-center gap-2 rounded-lg border border-emerald-200 bg-emerald-50 px-4 py-3">
              <IconCheckCircle className="h-5 w-5 shrink-0 text-emerald-600" />
              <div>
                <p className="text-sm font-semibold text-slate-900">Interview complete</p>
                <p className="text-sm text-slate-600">Score: {evaluation.score} / 100</p>
              </div>
            </div>

            <p className="text-sm leading-relaxed text-slate-700">{evaluation.feedback}</p>

            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
              <div>
                <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-emerald-700">
                  Strong topics
                </p>
                <div className="flex flex-wrap gap-1.5">
                  {evaluation.strong_topics.map((topic) => (
                    <span
                      key={topic}
                      className="rounded-full border border-emerald-200 bg-emerald-50 px-2.5 py-1 text-xs text-emerald-700"
                    >
                      {topic}
                    </span>
                  ))}
                </div>
              </div>
              <div>
                <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-500">
                  Needs work
                </p>
                <div className="flex flex-wrap gap-1.5">
                  {evaluation.weak_topics.map((topic) => (
                    <span
                      key={topic}
                      className="rounded-full border border-slate-200 bg-slate-50 px-2.5 py-1 text-xs text-slate-600"
                    >
                      {topic}
                    </span>
                  ))}
                </div>
              </div>
            </div>

            <div className="flex flex-col gap-2">
              <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">
                Question breakdown
              </p>
              {evaluation.per_question.map((item, index) => (
                <div key={index} className="rounded-lg border border-emerald-100 bg-white p-3">
                  <div className="flex items-start justify-between gap-3">
                    <p className="text-sm text-slate-800">{item.question}</p>
                    <span className="shrink-0 rounded-full bg-emerald-50 px-2 py-0.5 text-xs font-medium text-emerald-700">
                      {item.score}/10
                    </span>
                  </div>
                  <p className="mt-1 text-xs text-slate-500">{item.verdict}</p>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </main>
  );
}
