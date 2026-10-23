
"use client";

import { useState } from "react";
import { useAuth } from "@clerk/nextjs";

type BackendUser = {
  user_id: string;
};

export default function BackendAuthCheck() {
  const { isLoaded, isSignedIn, getToken } = useAuth();
  const [user, setUser] = useState<BackendUser | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function checkBackend() {
    setLoading(true);
    setError("");
    setUser(null);

    try {
      const token = await getToken();

      if (!token) {
        throw new Error("No Clerk session token is available.");
      }

      const response = await fetch(
        `${process.env.NEXT_PUBLIC_API_URL}/api/me`,
        {
          headers: {
            Authorization: `Bearer ${token}`,
          },
        },
      );

      const data = await response.json();

      if (!response.ok) {
        throw new Error(data.detail ?? "Backend authentication failed.");
      }

      setUser(data as BackendUser);
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Could not connect to the backend.",
      );
    } finally {
      setLoading(false);
    }
  }

  if (!isLoaded) {
    return <p className="text-sm text-slate-500">Loading authentication…</p>;
  }

  if (!isSignedIn) {
    return (
      <p className="text-sm text-slate-500">
        Sign in to test the backend connection.
      </p>
    );
  }

  return (
    <section className="rounded-2xl border border-slate-200 bg-white p-5">
      <h2 className="text-lg font-semibold text-slate-900">
        Backend authentication
      </h2>
      <p className="mt-1 text-sm text-slate-600">
        Verify that FastAPI recognizes your Clerk session.
      </p>

      <button
        type="button"
        onClick={checkBackend}
        disabled={loading}
        className="mt-4 rounded-lg bg-violet-600 px-4 py-2 text-sm font-semibold text-white disabled:opacity-60"
      >
        {loading ? "Checking…" : "Test backend connection"}
      </button>

      {user && (
        <p className="mt-4 break-all text-sm text-emerald-700">
          Authenticated successfully. Backend user ID: {user.user_id}
        </p>
      )}

      {error && (
        <p role="alert" className="mt-4 break-words text-sm text-red-600">
          {error}
        </p>
      )}
    </section>
  );
}
