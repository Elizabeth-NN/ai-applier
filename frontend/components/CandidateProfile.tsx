"use client";

import { useAuth } from "@clerk/nextjs";
import { useCallback, useEffect, useState, type FormEvent } from "react";
import { FloppyDisk, UserCircle, ShieldCheck } from "@phosphor-icons/react";

type CandidateProfileData = {
  id?: number;
  full_name: string;
  headline: string;
  email: string;
  phone: string;
  location: string;
  professional_summary: string;
  skills: string[];
  experience: Record<string, unknown>[];
  education: Record<string, unknown>[];
  projects: Record<string, unknown>[];
  certifications: Record<string, unknown>[];
  links: Record<string, string>;
  target_roles: string[];
  work_preferences: Record<string, unknown>;
  created_at?: string;
  updated_at?: string;
};

type JsonField =
  | "experience"
  | "education"
  | "projects"
  | "certifications"
  | "links"
  | "work_preferences";

const emptyProfile: CandidateProfileData = {
  full_name: "",
  headline: "",
  email: "",
  phone: "",
  location: "",
  professional_summary: "",
  skills: [],
  experience: [],
  education: [],
  projects: [],
  certifications: [],
  links: {},
  target_roles: [],
  work_preferences: {},
};

const jsonFieldLabels: { key: JsonField; label: string; description: string }[] = [
  {
    key: "experience",
    label: "Work experience",
    description:
      'Add one JSON object per role. Example: {"company":"Example Ltd","title":"Software Engineer","description":"Built APIs","start_date":"2025-01","end_date":"2025-06"}',
  },
  {
    key: "education",
    label: "Education",
    description:
      'Example: {"institution":"Moringa School","qualification":"Software Engineering","start_date":"2024","end_date":"2025"}',
  },
  {
    key: "projects",
    label: "Projects",
    description:
      'Example: {"name":"AI Applier","description":"Job application assistant","url":"https://github.com/example/project"}',
  },
  {
    key: "certifications",
    label: "Certifications",
    description:
      'Example: {"name":"Python Certification","issuer":"Example Provider","date":"2025"}',
  },
  {
    key: "links",
    label: "Professional links",
    description:
      'Enter a JSON object such as {"github":"https://github.com/username","linkedin":"https://linkedin.com/in/username","portfolio":"https://example.com"}.',
  },
  {
    key: "work_preferences",
    label: "Work preferences",
    description:
      'Example: {"remote":true,"employment_type":["full-time","contract"],"preferred_locations":["Remote"]}.',
  },
];

async function apiRequest<T>(
  path: string,
  token: string,
  options: RequestInit = {},
): Promise<T> {
  const apiUrl = process.env.NEXT_PUBLIC_API_URL;

  if (!apiUrl) {
    throw new Error("NEXT_PUBLIC_API_URL is not configured.");
  }

  const response = await fetch(`${apiUrl.replace(/\/$/, "")}${path}`, {
    ...options,
    headers: {
      Authorization: `Bearer ${token}`,
      ...(options.body ? { "Content-Type": "application/json" } : {}),
      ...options.headers,
    },
  });

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

function parseStringList(value: string): string[] {
  return value
    .split(/[\n,]/)
    .map((item) => item.trim())
    .filter(Boolean);
}

function parseJsonField(
  key: JsonField,
  value: string,
): Record<string, unknown>[] | Record<string, string> | Record<string, unknown> {
  let parsed: unknown;

  try {
    parsed = JSON.parse(value);
  } catch {
    throw new Error(`${key.replaceAll("_", " ")} must contain valid JSON.`);
  }

  if (key === "links" || key === "work_preferences") {
    if (
      parsed === null ||
      Array.isArray(parsed) ||
      typeof parsed !== "object"
    ) {
      throw new Error(`${key.replaceAll("_", " ")} must be a JSON object.`);
    }
    return parsed as Record<string, string> | Record<string, unknown>;
  }

  if (
    !Array.isArray(parsed) ||
    parsed.some(
      (item) =>
        item === null || Array.isArray(item) || typeof item !== "object",
    )
  ) {
    throw new Error(`${key.replaceAll("_", " ")} must be a JSON array of objects.`);
  }

  return parsed as Record<string, unknown>[];
}

export default function CandidateProfile() {
  const { isLoaded, isSignedIn, getToken } = useAuth();

  const [profile, setProfile] =
    useState<CandidateProfileData>(emptyProfile);
  const [listValues, setListValues] = useState({
    skills: "",
    target_roles: "",
  });
  const [jsonValues, setJsonValues] = useState<Record<JsonField, string>>({
    experience: "[]",
    education: "[]",
    projects: "[]",
    certifications: "[]",
    links: "{}",
    work_preferences: "{}",
  });
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  const loadProfile = useCallback(async () => {
    if (!isLoaded || !isSignedIn) return;

    try {
      const token = await getToken();
      setError("");

      if (!token) {
        throw new Error("Your session has expired. Please sign in again.");
      }

      const data = await apiRequest<CandidateProfileData | null>(
        "/api/candidate-profile",
        token,
      );

      const loaded = data ?? emptyProfile;

      setProfile({ ...emptyProfile, ...loaded });
      setListValues({
        skills: (loaded.skills ?? []).join(", "),
        target_roles: (loaded.target_roles ?? []).join(", "),
      });
      setJsonValues({
        experience: JSON.stringify(loaded.experience ?? [], null, 2),
        education: JSON.stringify(loaded.education ?? [], null, 2),
        projects: JSON.stringify(loaded.projects ?? [], null, 2),
        certifications: JSON.stringify(loaded.certifications ?? [], null, 2),
        links: JSON.stringify(loaded.links ?? {}, null, 2),
        work_preferences: JSON.stringify(
          loaded.work_preferences ?? {},
          null,
          2,
        ),
      });
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Could not load your profile.",
      );
    } finally {
      setLoading(false);
    }
  }, [getToken, isLoaded, isSignedIn]);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      void loadProfile();
    }, 0);

    return () => window.clearTimeout(timer);
  }, [loadProfile]);

  function updateText(
    field: keyof Pick<
      CandidateProfileData,
      | "full_name"
      | "headline"
      | "email"
      | "phone"
      | "location"
      | "professional_summary"
    >,
    value: string,
  ) {
    setProfile((current) => ({ ...current, [field]: value }));
  }

  async function handleSave(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    setNotice("");

    let structuredFields: Partial<CandidateProfileData>;

    try {
      structuredFields = {
        experience: parseJsonField("experience", jsonValues.experience) as Record<string, unknown>[],
        education: parseJsonField("education", jsonValues.education) as Record<string, unknown>[],
        projects: parseJsonField("projects", jsonValues.projects) as Record<string, unknown>[],
        certifications: parseJsonField("certifications", jsonValues.certifications) as Record<string, unknown>[],
        links: parseJsonField("links", jsonValues.links) as Record<string, string>,
        work_preferences: parseJsonField("work_preferences", jsonValues.work_preferences) as Record<string, unknown>,
      };
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Check the structured profile data.",
      );
      return;
    }

    const payload: CandidateProfileData = {
      ...profile,
      ...structuredFields,
      skills: parseStringList(listValues.skills),
      target_roles: parseStringList(listValues.target_roles),
    };

    setSaving(true);

    try {
      const token = await getToken();
      if (!token) {
        throw new Error("Your session has expired. Please sign in again.");
      }

      const saved = await apiRequest<CandidateProfileData>(
        "/api/candidate-profile",
        token,
        {
          method: "PUT",
          body: JSON.stringify(payload),
        },
      );

      setProfile({ ...emptyProfile, ...saved });
      setListValues({
        skills: (saved.skills ?? []).join(", "),
        target_roles: (saved.target_roles ?? []).join(", "),
      });
      setJsonValues({
        experience: JSON.stringify(saved.experience ?? [], null, 2),
        education: JSON.stringify(saved.education ?? [], null, 2),
        projects: JSON.stringify(saved.projects ?? [], null, 2),
        certifications: JSON.stringify(saved.certifications ?? [], null, 2),
        links: JSON.stringify(saved.links ?? {}, null, 2),
        work_preferences: JSON.stringify(
          saved.work_preferences ?? {},
          null,
          2,
        ),
      });
      setNotice("Your candidate profile has been saved.");
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Could not save your profile.",
      );
    } finally {
      setSaving(false);
    }
  }

  if (!isLoaded) {
    return (
      <p className="rounded-xl border border-slate-200 bg-white p-5 text-sm text-slate-500">
        Loading your candidate profile…
      </p>
    );
  }

  if (!isSignedIn) {
    return (
      <p className="rounded-xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-800">
        Sign in to manage your candidate profile.
      </p>
    );
  }

  if (loading) {
    return (
      <p className="rounded-xl border border-slate-200 bg-white p-5 text-sm text-slate-500">
        Loading your candidate profile…
      </p>
    );
  }

  const inputClass =
    "mt-1.5 w-full rounded-xl border border-slate-200 bg-white px-3 py-2.5 text-sm font-normal text-slate-800 outline-none transition placeholder:text-slate-400 focus:border-violet-400 focus:ring-2 focus:ring-violet-100";

  return (
    <div className="space-y-6 pb-8">
      <section className="rounded-2xl border border-violet-100 bg-violet-50/60 p-4 sm:p-5">
        <div className="flex items-start gap-3">
          <ShieldCheck size={24} className="mt-0.5 shrink-0 text-violet-700" />
          <div>
            <h2 className="font-bold text-slate-900">
              Your professional profile
            </h2>
            <p className="mt-1 text-sm leading-relaxed text-slate-600">
              Maintain the information you want AI Applier to use when
              preparing job applications. You control what is stored and can
              edit it at any time. Saving this profile does not submit
              applications or change your uploaded resumes.
            </p>
          </div>
        </div>
      </section>

      {error && (
        <p
          role="alert"
          className="rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700"
        >
          {error}
        </p>
      )}

      {notice && (
        <p
          role="status"
          className="rounded-xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-700"
        >
          {notice}
        </p>
      )}

      <form onSubmit={handleSave} className="space-y-6">
        <section className="rounded-2xl border border-slate-200 bg-white p-5 sm:p-6">
          <div className="mb-5 flex items-center gap-3">
            <UserCircle size={25} className="text-violet-600" />
            <div>
              <h2 className="text-lg font-extrabold text-slate-900">
                Personal details
              </h2>
              <p className="text-sm text-slate-500">
                Basic information employers may need to contact you.
              </p>
            </div>
          </div>

          <div className="grid gap-4 sm:grid-cols-2">
            {(
              [
                ["full_name", "Full name", "Your name"],
                ["headline", "Professional headline", "e.g. Junior Software Developer"],
                ["email", "Email address", "you@example.com"],
                ["phone", "Phone number", "+254..."],
                ["location", "Location", "e.g. Nairobi, Kenya"],
              ] as const
            ).map(([field, label, placeholder]) => (
              <label
                key={field}
                className="block text-sm font-semibold text-slate-700"
              >
                {label}
                <input
                  type={field === "email" ? "email" : "text"}
                  maxLength={
                    field === "email" ? 320 : field === "phone" ? 50 : 255
                  }
                  value={profile[field]}
                  onChange={(event) => updateText(field, event.target.value)}
                  placeholder={placeholder}
                  className={inputClass}
                />
              </label>
            ))}

            <label className="block text-sm font-semibold text-slate-700 sm:col-span-2">
              Professional summary
              <textarea
                rows={5}
                maxLength={10000}
                value={profile.professional_summary}
                onChange={(event) =>
                  updateText("professional_summary", event.target.value)
                }
                placeholder="Summarise your experience, strengths and career goals..."
                className={inputClass}
              />
              <span className="mt-1 block text-xs font-normal text-slate-400">
                Maximum 10,000 characters.
              </span>
            </label>
          </div>
        </section>

        <section className="rounded-2xl border border-slate-200 bg-white p-5 sm:p-6">
          <h2 className="text-lg font-extrabold text-slate-900">
            Skills and target roles
          </h2>
          <p className="mt-1 text-sm text-slate-500">
            Separate items with commas or new lines.
          </p>

          <div className="mt-4 space-y-4">
            <label className="block text-sm font-semibold text-slate-700">
              Skills
              <textarea
                rows={3}
                value={listValues.skills}
                onChange={(event) =>
                  setListValues((current) => ({
                    ...current,
                    skills: event.target.value,
                  }))
                }
                placeholder="Python, FastAPI, React, PostgreSQL..."
                className={inputClass}
              />
            </label>

            <label className="block text-sm font-semibold text-slate-700">
              Target job roles
              <textarea
                rows={2}
                value={listValues.target_roles}
                onChange={(event) =>
                  setListValues((current) => ({
                    ...current,
                    target_roles: event.target.value,
                  }))
                }
                placeholder="Junior Python Developer, Backend Developer..."
                className={inputClass}
              />
            </label>
          </div>
        </section>

        <section className="rounded-2xl border border-slate-200 bg-white p-5 sm:p-6">
          <h2 className="text-lg font-extrabold text-slate-900">
            Experience, education and more
          </h2>
          <p className="mt-1 text-sm leading-relaxed text-slate-500">
            These sections use JSON so you can preserve different types of
            experience and qualifications. Keep each entry as an object.
          </p>

          <div className="mt-5 space-y-5">
            {jsonFieldLabels.map(({ key, label, description }) => (
              <label
                key={key}
                className="block text-sm font-semibold text-slate-700"
              >
                {label}
                <span className="mt-1 block text-xs font-normal leading-relaxed text-slate-500">
                  {description}
                </span>
                <textarea
                  rows={key === "work_preferences" ? 5 : 7}
                  spellCheck={false}
                  value={jsonValues[key]}
                  onChange={(event) =>
                    setJsonValues((current) => ({
                      ...current,
                      [key]: event.target.value,
                    }))
                  }
                  className={`${inputClass} resize-y font-mono text-xs leading-relaxed`}
                />
              </label>
            ))}
          </div>
        </section>

        <div className="flex flex-wrap items-center justify-between gap-3">
          <p className="text-xs text-slate-500">
            Save your changes when you are ready. All profile sections are
            saved together.
          </p>
          <button
            type="submit"
            disabled={saving}
            className="inline-flex items-center justify-center gap-2 rounded-xl bg-violet-600 px-5 py-3 text-sm font-bold text-white transition hover:bg-violet-700 disabled:cursor-not-allowed disabled:opacity-60"
          >
            <FloppyDisk size={18} />
            {saving ? "Saving profile…" : "Save profile"}
          </button>
        </div>
      </form>
    </div>
  );
}
