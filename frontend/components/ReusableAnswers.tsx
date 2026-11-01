"use client";

import { useAuth } from "@clerk/nextjs";
import { useCallback, useEffect, useState, type FormEvent } from "react";
import {
  CheckCircle,
  Clock,
  PencilSimple,
  Plus,
  ShieldCheck,
  Trash,
  X,
} from "@phosphor-icons/react";

type CandidateAnswer = {
  id: number;
  question_key: string;
  question_label: string;
  answer: string;
  is_user_authored: boolean;
  is_approved: boolean;
  created_at: string;
  updated_at: string;
};

async function apiRequest<T>(
  path: string,
  token: string,
  options: RequestInit = {},
): Promise<T> {
  const apiUrl = process.env.NEXT_PUBLIC_API_URL;

  if (!apiUrl) {
    throw new Error("NEXT_PUBLIC_API_URL is not configured.");
  }

  const response = await fetch(
    `${apiUrl.replace(/\/$/, "")}${path}`,
    {
      ...options,
      headers: {
        Authorization: `Bearer ${token}`,
        ...(options.body ? { "Content-Type": "application/json" } : {}),
        ...options.headers,
      },
    },
  );

  const data = await response.json().catch(() => null);

  if (!response.ok) {
    throw new Error(
      data && typeof data.detail === "string"
        ? data.detail
        : `Request failed (${response.status}).`,
    );
  }

  return data as T;
}

function makeQuestionKey(label: string): string {
  const key = label
    .normalize("NFKD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "_")
    .replace(/^_+|_+$/g, "")
    .slice(0, 80)
    .replace(/_+$/g, "");

  return key.length >= 2 ? key : "";
}

export default function ReusableAnswers() {
  const { isLoaded, isSignedIn, getToken } = useAuth();

  const [answers, setAnswers] = useState<CandidateAnswer[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [actionId, setActionId] = useState<number | null>(null);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [questionLabel, setQuestionLabel] = useState("");
  const [answerText, setAnswerText] = useState("");
  const [confirmed, setConfirmed] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  const loadAnswers = useCallback(async () => {
    if (!isLoaded || !isSignedIn) return;

    setLoading(true);
    setError("");

    try {
      const token = await getToken();
      if (!token) throw new Error("Your session has expired. Please sign in again.");

      const data = await apiRequest<CandidateAnswer[]>(
        "/api/candidate-answers?skip=0&limit=100",
        token,
      );

      setAnswers(data);
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Could not load reusable answers.",
      );
    } finally {
      setLoading(false);
    }
  }, [getToken, isLoaded, isSignedIn]);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      void loadAnswers();
    }, 0);

    return () => window.clearTimeout(timer);
  }, [loadAnswers]);

  function resetForm() {
    setEditingId(null);
    setQuestionLabel("");
    setAnswerText("");
    setConfirmed(false);
  }

  function startEditing(item: CandidateAnswer) {
    setEditingId(item.id);
    setQuestionLabel(item.question_label);
    setAnswerText(item.answer);
    setConfirmed(false);
    setError("");
    setNotice("");
    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  async function handleSave(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    setNotice("");

    if (!confirmed) {
      setError("Please confirm that this answer is written in your own words.");
      return;
    }

    const label = questionLabel.trim();
    const text = answerText.trim();

    if (!label || !text) {
      setError("Enter both a question label and an answer.");
      return;
    }

    if (label.length > 255 || text.length > 10000) {
      setError("The question label must be at most 255 characters and the answer at most 10,000.");
      return;
    }

    const questionKey = makeQuestionKey(label);

    if (editingId === null && !questionKey) {
      setError("Please use a question label containing at least two letters or numbers.");
      return;
    }

    setSaving(true);

    try {
      const token = await getToken();
      if (!token) throw new Error("Your session has expired. Please sign in again.");

      if (editingId !== null) {
        await apiRequest<CandidateAnswer>(
          `/api/candidate-answers/${editingId}`,
          token,
          {
            method: "PATCH",
            body: JSON.stringify({
              question_label: label,
              answer: text,
              confirm_user_authored: true,
            }),
          },
        );
        setNotice("Answer updated. It is pending approval again.");
      } else {
        await apiRequest<CandidateAnswer>("/api/candidate-answers", token, {
          method: "POST",
          body: JSON.stringify({
            question_key: questionKey,
            question_label: label,
            answer: text,
            confirm_user_authored: true,
          }),
        });
        setNotice("Answer saved. Review and approve it before reuse.");
      }

      resetForm();
      await loadAnswers();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not save this answer.");
    } finally {
      setSaving(false);
    }
  }

  async function approveAnswer(id: number) {
    setActionId(id);
    setError("");
    setNotice("");

    try {
      const token = await getToken();
      if (!token) throw new Error("Your session has expired. Please sign in again.");

      await apiRequest<CandidateAnswer>(
        `/api/candidate-answers/${id}/approve`,
        token,
        { method: "POST" },
      );

      setNotice("Answer approved for optional reuse during application preparation.");
      await loadAnswers();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not approve this answer.");
    } finally {
      setActionId(null);
    }
  }

  async function deleteAnswer(item: CandidateAnswer) {
    if (!window.confirm(`Delete the answer for "${item.question_label}"? This cannot be undone.`)) {
      return;
    }

    setActionId(item.id);
    setError("");
    setNotice("");

    try {
      const token = await getToken();
      if (!token) throw new Error("Your session has expired. Please sign in again.");

      await apiRequest<null>(
        `/api/candidate-answers/${item.id}`,
        token,
        { method: "DELETE" },
      );

      if (editingId === item.id) resetForm();
      setNotice("Reusable answer deleted.");
      await loadAnswers();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not delete this answer.");
    } finally {
      setActionId(null);
    }
  }

  const pendingAnswers = answers.filter((item) => !item.is_approved);
  const approvedAnswers = answers.filter(
    (item) => item.is_user_authored && item.is_approved,
  );

  if (!isLoaded) {
    return <p className="text-sm text-slate-500">Loading your account…</p>;
  }

  if (!isSignedIn) {
    return (
      <p className="rounded-xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-800">
        Sign in to manage your reusable answers.
      </p>
    );
  }

  return (
    <div className="space-y-6 pb-8">
      <section className="rounded-2xl border border-violet-100 bg-violet-50/60 p-4 sm:p-5">
        <div className="flex items-start gap-3">
          <ShieldCheck size={24} className="mt-0.5 shrink-0 text-violet-700" />
          <div>
            <h2 className="font-bold text-slate-900">Your words, your approval</h2>
            <p className="mt-1 text-sm leading-relaxed text-slate-600">
              Save answers that you have personally written. New and edited
              answers require your approval before they can be selected for an
              application. Nothing is submitted automatically.
            </p>
          </div>
        </div>
      </section>

      <section className="rounded-2xl border border-slate-200 bg-white p-5 sm:p-6">
        <div className="mb-5 flex items-center justify-between gap-3">
          <div>
            <h2 className="text-lg font-extrabold text-slate-900">
              {editingId === null ? "Add a reusable answer" : "Edit reusable answer"}
            </h2>
            <p className="mt-1 text-sm text-slate-500">
              Write the answer exactly as you would give it to an employer.
            </p>
          </div>
          {editingId !== null && (
            <button
              type="button"
              onClick={resetForm}
              className="flex items-center gap-1 rounded-lg px-3 py-2 text-sm font-semibold text-slate-500 hover:bg-slate-100"
            >
              <X size={16} /> Cancel
            </button>
          )}
        </div>

        <form onSubmit={handleSave} className="space-y-4">
          <div>
            <label htmlFor="candidate-question" className="mb-1.5 block text-sm font-semibold text-slate-700">
              Application question
            </label>
            <input
              id="candidate-question"
              value={questionLabel}
              onChange={(event) => setQuestionLabel(event.target.value)}
              maxLength={255}
              placeholder="e.g. Why are you interested in this role?"
              required
              className="w-full rounded-xl border border-slate-200 bg-white px-4 py-3 text-sm text-slate-900 outline-none transition focus:border-violet-400 focus:ring-2 focus:ring-violet-100"
            />
          </div>

          <div>
            <label htmlFor="candidate-answer" className="mb-1.5 block text-sm font-semibold text-slate-700">
              Your answer
            </label>
            <textarea
              id="candidate-answer"
              value={answerText}
              onChange={(event) => setAnswerText(event.target.value)}
              maxLength={10000}
              rows={6}
              placeholder="Write your own answer here…"
              required
              className="w-full resize-y rounded-xl border border-slate-200 bg-white px-4 py-3 text-sm leading-relaxed text-slate-900 outline-none transition focus:border-violet-400 focus:ring-2 focus:ring-violet-100"
            />
            <p className="mt-1 text-right text-xs text-slate-400">
              {answerText.length.toLocaleString()} / 10,000
            </p>
          </div>

          <label className="flex cursor-pointer items-start gap-3 rounded-xl border border-slate-200 p-3">
            <input
              type="checkbox"
              checked={confirmed}
              onChange={(event) => setConfirmed(event.target.checked)}
              className="mt-1 h-4 w-4 accent-violet-600"
            />
            <span className="text-sm leading-relaxed text-slate-700">
              I confirm that this answer is written by me in my own words. It
              is not AI-generated, copied, or written by someone else.
            </span>
          </label>

          <button
            type="submit"
            disabled={saving || !confirmed}
            className="inline-flex items-center justify-center gap-2 rounded-xl bg-violet-600 px-5 py-3 text-sm font-bold text-white transition hover:bg-violet-700 disabled:cursor-not-allowed disabled:opacity-50"
          >
            <Plus size={17} />
            {saving ? "Saving…" : editingId === null ? "Save for review" : "Save changes"}
          </button>
        </form>
      </section>

      {error && (
        <p role="alert" className="rounded-xl border border-rose-200 bg-rose-50 p-3 text-sm text-rose-700">
          {error}
        </p>
      )}
      {notice && (
        <p role="status" className="rounded-xl border border-emerald-200 bg-emerald-50 p-3 text-sm text-emerald-700">
          {notice}
        </p>
      )}

      {loading ? (
        <p className="py-6 text-center text-sm text-slate-500">Loading reusable answers…</p>
      ) : (
        <>
          <section className="space-y-3">
            <div className="flex items-center justify-between gap-3">
              <div>
                <h2 className="text-lg font-extrabold text-slate-900">Awaiting your approval</h2>
                <p className="text-sm text-slate-500">Review each answer before making it reusable.</p>
              </div>
              <span className="rounded-full bg-amber-50 px-3 py-1 text-xs font-bold text-amber-700">
                {pendingAnswers.length} pending
              </span>
            </div>

            {pendingAnswers.length === 0 ? (
              <div className="rounded-2xl border border-dashed border-slate-300 bg-white p-6 text-center">
                <Clock size={25} className="mx-auto text-slate-400" />
                <p className="mt-2 text-sm text-slate-600">No answers awaiting approval.</p>
              </div>
            ) : (
              pendingAnswers.map((item) => (
                <article key={item.id} className="rounded-2xl border border-amber-200 bg-white p-4 sm:p-5">
                  <div className="flex flex-wrap items-start justify-between gap-3">
                    <div className="min-w-0 flex-1">
                      <h3 className="font-bold text-slate-900">{item.question_label}</h3>
                      <p className="mt-2 whitespace-pre-wrap break-words text-sm leading-relaxed text-slate-600">
                        {item.answer}
                      </p>
                      <span className="mt-3 inline-flex rounded-full bg-amber-50 px-2.5 py-1 text-xs font-semibold text-amber-700">
                        Pending approval
                      </span>
                    </div>
                  </div>
                  <div className="mt-4 flex flex-wrap gap-2 border-t border-slate-100 pt-3">
                    <button
                      type="button"
                      onClick={() => void approveAnswer(item.id)}
                      disabled={actionId !== null}
                      className="inline-flex items-center gap-2 rounded-lg bg-violet-600 px-3 py-2 text-xs font-bold text-white hover:bg-violet-700 disabled:opacity-50"
                    >
                      <CheckCircle size={16} />
                      {actionId === item.id ? "Please wait…" : "Approve for reuse"}
                    </button>
                    <button
                      type="button"
                      onClick={() => startEditing(item)}
                      disabled={actionId !== null}
                      className="inline-flex items-center gap-2 rounded-lg border border-slate-200 px-3 py-2 text-xs font-semibold text-slate-600 hover:bg-slate-50 disabled:opacity-50"
                    >
                      <PencilSimple size={16} /> Edit
                    </button>
                    <button
                      type="button"
                      onClick={() => void deleteAnswer(item)}
                      disabled={actionId !== null}
                      className="inline-flex items-center gap-2 rounded-lg border border-rose-100 px-3 py-2 text-xs font-semibold text-rose-600 hover:bg-rose-50 disabled:opacity-50"
                    >
                      <Trash size={16} /> Delete
                    </button>
                  </div>
                </article>
              ))
            )}
          </section>

          <section className="space-y-3">
            <div className="flex items-center justify-between gap-3">
              <div>
                <h2 className="text-lg font-extrabold text-slate-900">Approved answers</h2>
                <p className="text-sm text-slate-500">These can be selected during application preparation.</p>
              </div>
              <span className="rounded-full bg-emerald-50 px-3 py-1 text-xs font-bold text-emerald-700">
                {approvedAnswers.length} approved
              </span>
            </div>

            {approvedAnswers.length === 0 ? (
              <div className="rounded-2xl border border-dashed border-slate-300 bg-white p-6 text-center">
                <ShieldCheck size={25} className="mx-auto text-slate-400" />
                <p className="mt-2 text-sm text-slate-600">
                  No approved answers yet. Add an answer above, then approve it here.
                </p>
              </div>
            ) : (
              approvedAnswers.map((item) => (
                <article key={item.id} className="rounded-2xl border border-emerald-200 bg-white p-4 sm:p-5">
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0 flex-1">
                      <h3 className="font-bold text-slate-900">{item.question_label}</h3>
                      <p className="mt-2 whitespace-pre-wrap break-words text-sm leading-relaxed text-slate-600">
                        {item.answer}
                      </p>
                      <span className="mt-3 inline-flex rounded-full bg-emerald-50 px-2.5 py-1 text-xs font-semibold text-emerald-700">
                        User-authored · Approved
                      </span>
                    </div>
                  </div>
                  <div className="mt-4 flex flex-wrap gap-2 border-t border-slate-100 pt-3">
                    <button
                      type="button"
                      onClick={() => startEditing(item)}
                      className="inline-flex items-center gap-2 rounded-lg border border-slate-200 px-3 py-2 text-xs font-semibold text-slate-600 hover:bg-slate-50"
                    >
                      <PencilSimple size={16} /> Edit
                    </button>
                    <button
                      type="button"
                      onClick={() => void deleteAnswer(item)}
                      disabled={actionId !== null}
                      className="inline-flex items-center gap-2 rounded-lg border border-rose-100 px-3 py-2 text-xs font-semibold text-rose-600 hover:bg-rose-50 disabled:opacity-50"
                    >
                      <Trash size={16} /> Delete
                    </button>
                  </div>
                </article>
              ))
            )}
          </section>
        </>
      )}
    </div>
  );
}
