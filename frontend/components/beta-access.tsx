import Link from "next/link";
import { Account } from "@/lib/api";

export function BetaAccessNotice({
  user,
  refresh,
}: {
  user: Account;
  refresh?: () => void;
}) {
  return (
    <section className="panel" aria-label="Signal access">
      <h2>Analyze a Call</h2>
      <p>
        Upload calls to automatically transcribe, evaluate, and extract call
        intelligence.
      </p>
      <button className="button primary" disabled>
        {user.operational_access && !user.can_review
          ? "Upload unavailable for your role"
          : "Beta access required"}
      </button>
      <p>
        {user.organization_suspended
          ? "Your organization's access is paused. Contact your administrator."
          : !user.organization_id
            ? "Join or create an organization to request access to call analysis."
            : !user.can_review
              ? "Your role does not allow call upload or organization-wide reviews. Contact your administrator."
              : "Your organization does not currently have access to call analysis. Contact your administrator to request access."}
      </p>
      {!user.organization_id && (
        <Link href="/account">Join or create an organization</Link>
      )}
      {refresh && (
        <button className="button secondary" onClick={refresh}>
          Check access again
        </button>
      )}
    </section>
  );
}
