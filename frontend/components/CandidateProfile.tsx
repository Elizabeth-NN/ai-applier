"use client";

import { useAuth } from "@clerk/nextjs";
import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type FormEvent,
} from "react";
import {
  CheckCircle,
  FloppyDisk,
  UserCircle,
  ShieldCheck,
} from "@phosphor-icons/react";

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

/** Exactly what the PUT endpoint accepts (no id or timestamps). */
type CandidateProfilePayload = Omit<
  CandidateProfileData,
  "id" | "created_at" | "updated_at"
>;

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

/* -------------------------------------------------------------------------- */
/*  API helpers                                                               */
/* -------------------------------------------------------------------------- */

/** Turns FastAPI/Pydantic errors (string or array) into a readable message. */
function formatApiError(data: unknown, status: number): string {
  const detail = (data as { detail?: unknown } | null)?.detail;

  if (typeof detail === "string") return detail;

  if (Array.isArray(detail)) {
    const messages = detail.map((item) => {
      const { loc, msg } = (item ?? {}) as { loc?: unknown[]; msg?: unknown };
      const field = Array.isArray(loc)
        ? loc.filter((part) => part !== "body").join(" → ")
        : "";
      const text = typeof msg === "string" ? msg : "Invalid value";
      return field ? `${field}: ${text}` : text;
    });
    if (messages.length > 0) return messages.join("; ");
  }

  return `Request failed (${status}).`;
}

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
    throw new Error(formatApiError(data, response.status));
  }

  return data as T;
}

/* -------------------------------------------------------------------------- */
/*  Value helpers (the API can return null or JSON text for any field)        */
/* -------------------------------------------------------------------------- */

function parseStringList(value: string): string[] {
  return value
    .split(/[\n,]/)
    .map((item) => item.trim())
    .filter(Boolean);
}

function parseMaybeJson(value: unknown): unknown {
  if (typeof value === "string") {
    try {
      return JSON.parse(value);
    } catch {
      return value;
    }
  }
  return value;
}

function asString(value: unknown): string {
  return typeof value === "string" ? value : "";
}

function asStringList(value: unknown): string[] {
  const parsed = parseMaybeJson(value);
  if (Array.isArray(parsed)) {
    return parsed.filter((item): item is string => typeof item === "string");
  }
  return typeof parsed === "string" ? parseStringList(parsed) : [];
}

function asObjectList(value: unknown): Record<string, unknown>[] {
  const parsed = parseMaybeJson(value);
  return Array.isArray(parsed)
    ? (parsed.filter(
        (item) => item && typeof item === "object" && !Array.isArray(item),
      ) as Record<string, unknown>[])
    : [];
}

function asObject(value: unknown): Record<string, unknown> {
  const parsed = parseMaybeJson(value);
  return parsed && typeof parsed === "object" && !Array.isArray(parsed)
    ? (parsed as Record<string, unknown>)
    : {};
}

/** Guarantees every field has a usable value, whatever the API returned. */
function normalizeProfile(data: unknown): CandidateProfileData {
  const d = (data && typeof data === "object" ? data : {}) as Record<
    string,
    unknown
  >;

  return {
    id: typeof d.id === "number" ? d.id : undefined,
    full_name: asString(d.full_name),
    headline: asString(d.headline),
    email: asString(d.email),
    phone: asString(d.phone),
    location: asString(d.location),
    professional_summary: asString(d.professional_summary),
    skills: asStringList(d.skills),
    experience: asObjectList(d.experience),
    education: asObjectList(d.education),
    projects: asObjectList(d.projects),
    certifications: asObjectList(d.certifications),
    links: Object.fromEntries(
      Object.entries(asObject(d.links)).filter(
        ([, link]) => typeof link === "string",
      ),
    ) as Record<string, string>,
    target_roles: asStringList(d.target_roles),
    work_preferences: asObject(d.work_preferences),
    created_at: asString(d.created_at) || undefined,
    updated_at: asString(d.updated_at) || undefined,
  };
}

function parseJsonField(
  key: JsonField,
  value: string,
): Record<string, unknown>[] | Record<string, string> | Record<string, unknown> {
  const label = key.replaceAll("_", " ");
  let parsed: unknown;

  try {
    parsed = JSON.parse(value);
  } catch {
    throw new Error(`${label} must contain valid JSON.`);
  }

  if (key === "links" || key === "work_preferences") {
    if (
      parsed === null ||
      Array.isArray(parsed) ||
      typeof parsed !== "object"
    ) {
      throw new Error(`${label} must be a JSON object.`);
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
    throw new Error(`${label} must be a JSON array of objects.`);
  }

  return parsed as Record<string, unknown>[];
}

/** Stable string of everything the user can edit, used to detect changes. */
function serializeForm(
  profile: CandidateProfileData,
  listValues: { skills: string; target_roles: string },
  jsonValues: Record<JsonField, string>,
): string {
  return JSON.stringify({
    full_name: profile.full_name,
    headline: profile.headline,
    email: profile.email,
    phone: profile.phone,
    location: profile.location,
    professional_summary: profile.professional_summary,
    skills: listValues.skills,
    target_roles: listValues.target_roles,
    json: jsonValues,
  });
}

function formatSavedTime(iso: string | null): string {
  if (!iso) return "";
  const date = new Date(iso);
  return Number.isNaN(date.getTime()) ? "" : date.toLocaleString();
}

/* -------------------------------------------------------------------------- */
/*  Component                                                                 */
/* -------------------------------------------------------------------------- */

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
  const [savedSnapshot, setSavedSnapshot] = useState<string | null>(null);
  const [lastSaved, setLastSaved] = useState<string | null>(null);

  const messageRef = useRef<HTMLDivElement>(null);

  /** Puts a normalized profile into the form state and marks it as saved. */
  const applyProfile = useCallback((data: unknown, justSaved = false) => {
    const normalized = normalizeProfile(data);

    const nextList = {
      skills: normalized.skills.join(", "),
      target_roles: normalized.target_roles.join(", "),
    };
    const nextJson: Record<JsonField, string> = {
      experience: JSON.stringify(normalized.experience, null, 2),
      education: JSON.stringify(normalized.education, null, 2),
      projects: JSON.stringify(normalized.projects, null, 2),
      certifications: JSON.stringify(normalized.certifications, null, 2),
      links: JSON.stringify(normalized.links, null, 2),
      work_preferences: JSON.stringify(normalized.work_preferences, null, 2),
    };

    setProfile(normalized);
    setListValues(nextList);
    setJsonValues(nextJson);
    setSavedSnapshot(serializeForm(normalized, nextList, nextJson));
    setLastSaved(
      normalized.updated_at ?? (justSaved ? new Date().toISOString() : null),
    );
  }, []);

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

      applyProfile(data);
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Could not load your profile.",
      );
    } finally {
      setLoading(false);
    }
  }, [getToken, isLoaded, isSignedIn, applyProfile]);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      void loadProfile();
    }, 0);

    return () => window.clearTimeout(timer);
  }, [loadProfile]);

  // The Save button sits at the bottom of a long form, so bring the result
  // message into view whenever one appears.
  useEffect(() => {
    if (error || notice) {
      messageRef.current?.scrollIntoView({
        behavior: "smooth",
        block: "center",
      });
    }
  }, [error, notice]);

  const currentSnapshot = useMemo(
    () => serializeForm(profile, listValues, jsonValues),
    [profile, listValues, jsonValues],
  );
  const dirty = savedSnapshot !== null && currentSnapshot !== savedSnapshot;
  const hasSavedProfile = profile.id !== undefined;

  // Once the user edits again, the old "saved" message no longer applies.
  useEffect(() => {
    if (!dirty) return;

    const timer = window.setTimeout(() => {
      setNotice("");
    }, 0);

    return () => window.clearTimeout(timer);
  }, [dirty]);

  // Warn before leaving the page with unsaved edits.
  useEffect(() => {
    if (!dirty) return;

    function warn(event: BeforeUnloadEvent) {
      event.preventDefault();
    }

    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [dirty]);

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
    if (saving) return;

    setError("");
    setNotice("");

    const email = profile.email.trim();
    if (email && !/^\S+@\S+\.\S+$/.test(email)) {
      setError("Enter a valid email address, or leave it empty.");
      return;
    }

    let structuredFields: Pick<CandidateProfilePayload, JsonField>;

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

    // Send only the fields the API accepts: no id, no timestamps, no nulls.
    const payload: CandidateProfilePayload = {
      full_name: profile.full_name.trim(),
      headline: profile.headline.trim(),
      email,
      phone: profile.phone.trim(),
      location: profile.location.trim(),
      professional_summary: profile.professional_summary.trim(),
      skills: parseStringList(listValues.skills),
      target_roles: parseStringList(listValues.target_roles),
      ...structuredFields,
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

      applyProfile(saved, true);
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

      <div ref={messageRef} className="scroll-mt-28 space-y-3">
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
      </div>

      <form onSubmit={handleSave} noValidate className="space-y-6">
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

        <div className="sticky bottom-[calc(4.5rem+env(safe-area-inset-bottom))] z-10 flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-slate-200 bg-white/95 p-3 shadow-lg backdrop-blur sm:p-4 lg:bottom-4">
          <p
            role="status"
            aria-live="polite"
            className="flex items-center gap-2 text-xs sm:text-sm"
          >
            {saving ? (
              <span className="text-slate-500">Saving your profile…</span>
            ) : dirty ? (
              <>
                <span className="h-2 w-2 shrink-0 rounded-full bg-amber-500" />
                <span className="font-semibold text-amber-700">
                  Unsaved changes
                </span>
              </>
            ) : hasSavedProfile ? (
              <>
                <CheckCircle
                  size={18}
                  weight="fill"
                  className="shrink-0 text-emerald-500"
                />
                <span className="text-slate-600">
                  <span className="font-semibold text-emerald-700">
                    All changes saved
                  </span>
                  {formatSavedTime(lastSaved) && (
                    <span className="text-slate-400">
                      {" "}
                      · {formatSavedTime(lastSaved)}
                    </span>
                  )}
                </span>
              </>
            ) : (
              <span className="text-slate-500">
                Save your changes when you are ready. All profile sections are
                saved together.
              </span>
            )}
          </p>

          <button
            type="submit"
            disabled={saving || (!dirty && hasSavedProfile)}
            className={`inline-flex items-center justify-center gap-2 rounded-xl px-5 py-3 text-sm font-bold transition disabled:cursor-not-allowed ${
              !dirty && hasSavedProfile && !saving
                ? "bg-emerald-50 text-emerald-700"
                : "bg-violet-600 text-white hover:bg-violet-700 disabled:opacity-60"
            }`}
          >
            {!dirty && hasSavedProfile && !saving ? (
              <CheckCircle size={18} weight="fill" />
            ) : (
              <FloppyDisk size={18} />
            )}
            {saving
              ? "Saving profile…"
              : !dirty && hasSavedProfile
                ? "Saved"
                : "Save profile"}
          </button>
        </div>
      </form>
    </div>
  );
}