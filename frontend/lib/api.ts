export type User = {
  organization_name: string | null;
  organization_id: string | null;
  email_verified: boolean;
  id: string;
  name: string;
  email: string;
  role: string;
};
export type Account = User & {
  operational_access: boolean;
  can_review: boolean;
  subscription_status: string;
  entitlement_source: string | null;
  entitlement_expires_at: number | null;
  dev_activation_available: boolean;
  mail_delivery: string;
  checkout_available: boolean;
  onboarding_completed: boolean;
};

export function accountDestination(account: Account) {
  if (
    !account.email_verified ||
    !account.organization_id ||
    !account.operational_access ||
    !account.can_review
  )
    return "/account";
  return account.onboarding_completed ? "/" : "/onboarding";
}
export type Call = {
  audit_number: string | null;
  flagged: boolean;
  employee_id: string | null;
  employee_name: string | null;
  assignment_revision: number;
  evaluation_stale?: boolean;
  id: string;
  filename: string;
  created_at: number;
  duration: number | null;
  status: string;
  qa_score: number | null;
  ai_score?: number | null;
  has_overrides?: boolean;
  review_status?: string;
  size_bytes: number;
  is_demo: boolean;
  error: string | null;
  failed_stage: string | null;
};
export type Segment = {
  start: number | null;
  end: number | null;
  speaker: string | null;
  text: string;
};
export type ConversationTurn = {
  inferred_role?: string;
  manual_role?: string | null;
  effective_role?: "DISPATCHER" | "CALLER" | "UNKNOWN";
  corrector_name?: string | null;
  corrected_at?: number | null;
  start: number | null;
  end: number | null;
  text: string;
  speaker_id: string | null;
  speaker_role: "DISPATCHER" | "CALLER" | "UNKNOWN";
  role_source: "unknown" | "text_cue" | "speaker_context" | "provided_role";
  confidence: number | null;
  source_start: number;
  source_end: number;
  segment_indices: number[];
};
export type Conversation = {
  source_fingerprint?: string;
  revision?: number;
  history?: {
    id: number;
    source_start: number;
    source_end: number;
    inferred_role: string;
    previous_role: string;
    corrected_role: string | null;
    scope: string;
    actor_name: string;
    corrected_at: number;
  }[];
  version: string;
  inference_method: string;
  has_speaker_ids: boolean;
  alignment: "exact" | "full_text_fallback";
  turns: ConversationTurn[];
};
export type Detail = Call & {
  transcript: {
    text: string;
    segments: Segment[];
    provider: string;
    model: string;
    conversation?: Conversation;
  } | null;
  evaluation: {
    stale?: boolean;
    transcript_revision?: number;
    current_transcript_revision?: number;
    id: string;
    final_score: number;
    has_overrides: boolean;
    revision: number;
    reviewed_at: number | null;
    rubric_id: string;
    rubric_name: string;
    rubric: {
      key: string;
      label: string;
      max_score: number;
      criteria: string;
    }[];
    created_at: number;
    adjustments: {
      id: number;
      category_key: string;
      score: number | null;
      previous_score: number;
      reason: string;
      actor_name: string;
      changed_at: number;
    }[];
    overall_score: number;
    categories: {
      key: string;
      final_score: number;
      overridden: boolean;
      score: number;
      max_score: number;
      explanation: string;
      evidence: string[];
    }[];
    summary: string;
    strengths: string[];
    coaching_opportunities: string[];
    rubric_version: string;
    provider: string;
    model: string;
  } | null;
};
export type Config = {
  active_rubric_id: string;
  demo: boolean;
  max_upload_mb: number;
  rubric: { key: string; label: string; max_score: number }[];
};
export type Dashboard = {
  performance?: { stale: number; analyzed: number; limited_sample: boolean };
  total: number;
  processed: number;
  requiring_review: number;
  awaiting: number;
  failed: number;
  average_score: number | null;
  recent: Call[];
};

export class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
  ) {
    super(message);
  }
}
export async function api<T>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const response = await fetch(`/api${path}`, {
    ...options,
    cache: "no-store",
    credentials: "same-origin",
    headers: {
      "X-Drive-Request": "1",
      ...(options.body && !(options.body instanceof FormData)
        ? { "Content-Type": "application/json" }
        : {}),
      ...options.headers,
    },
  });
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    const message =
      typeof body?.detail === "string"
        ? body.detail
        : "The request could not be completed. Please try again.";
    if (
      response.status === 401 &&
      path !== "/auth/login" &&
      typeof window !== "undefined"
    )
      window.location.replace("/login");
    throw new ApiError(message, response.status);
  }
  return response.status === 204 ? (undefined as T) : response.json();
}
export const date = (seconds: number) =>
  new Date(seconds * 1000).toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
export const duration = (seconds: number | null) =>
  seconds === null
    ? "—"
    : `${Math.floor(seconds / 60)}:${Math.floor(seconds % 60)
        .toString()
        .padStart(2, "0")}`;
export const busy = (status: string) =>
  ["queued", "transcribing", "analyzing"].includes(status);

export type RubricCategory = {
  key?: string;
  name: string;
  description: string;
  weight: number;
  criteria: string;
};
export type Rubric = {
  id: string;
  name: string;
  version: string;
  status: string;
  revision: number;
  total_weight: number;
  created_at: number;
  activated_at: number | null;
  categories: RubricCategory[];
};
