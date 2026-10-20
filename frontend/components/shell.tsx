"use client";
import { createContext, useContext, useEffect, useState } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import {
  LayoutDashboard,
  Headphones,
  Upload,
  LogOut,
  ShieldCheck,
  Radio,
  BookOpen,
} from "lucide-react";
import { api, Account, Config } from "@/lib/api";
import { BetaAccessNotice } from "./beta-access";
import { Appearance } from "./preferences";
import { Brand, ErrorBox, Loading } from "./ui";

const Context = createContext<{ user: Account; config: Config } | null>(null);
export function useDrive() {
  const value = useContext(Context);
  if (!value) throw new Error("Missing Signal session");
  return value;
}
export function Shell({ children }: { children: React.ReactNode }) {
  const [session, setSession] = useState<{
    user: Account;
    config: Config;
  } | null>(null);
  const [error, setError] = useState("");
  const pathname = usePathname();
  const router = useRouter();
  useEffect(() => {
    let active = true;
    api<Account>("/account")
      .then(async (user) => {
        if (!user.email_verified) {
          router.replace("/verify-email");
          return;
        }
        const config = await api<Config>("/config");
        if (active) setSession({ user, config });
      })
      .catch((e) => {
        if (active) setError(e.message);
      });
    return () => {
      active = false;
    };
  }, [router]);
  async function refreshAccess() {
    try {
      const user = await api<Account>("/account");
      setSession((previous) => (previous ? { ...previous, user } : previous));
    } catch (e) {
      setError((e as Error).message);
    }
  }
  useEffect(() => {
    const refresh = () => {
      void refreshAccess();
    };
    const timer = setInterval(refresh, 15000);
    window.addEventListener("focus", refresh);
    return () => {
      clearInterval(timer);
      window.removeEventListener("focus", refresh);
    };
  }, []);
  async function logout() {
    try {
      await api("/auth/logout", { method: "POST" });
      router.replace("/login");
    } catch (e) {
      setError((e as Error).message);
    }
  }
  if (!session)
    return (
      <main className="session-loading">
        <Brand />
        {error ? <ErrorBox message={error} /> : <Loading />}
      </main>
    );
  return (
    <Context.Provider value={session}>
      <div className="app-shell">
        <aside className="sidebar">
          <Link href="/" aria-label="Signal overview">
            <Brand />
          </Link>
          <div className="nav-label">WORKSPACE</div>
          {session.user.is_platform_admin && (
            <Link href="/platform">Platform administration</Link>
          )}
          <nav aria-label="Workspace">
            {session.user.is_platform_admin && (
              <Link href="/platform">Zoqari Admin</Link>
            )}
            {[
              { href: "/", title: "Dashboard", Icon: LayoutDashboard },
              { href: "/calls", title: "Calls / Audits", Icon: Headphones },
              { href: "/upload", title: "Upload call", Icon: Upload },
              { href: "/batches", title: "Bulk upload", Icon: Upload },
              { href: "/employees", title: "Employees", Icon: Headphones },
            ].map(({ href, title, Icon }) => (
              <Link
                key={href}
                href={href}
                className={
                  (href === "/" ? pathname === "/" : pathname.startsWith(href))
                    ? "active"
                    : ""
                }
              >
                <Icon size={19} />
                {title}
              </Link>
            ))}
          </nav>
          <div className="nav-label">
            {["ADMIN", "OWNER"].includes(session.user.role)
              ? "ADMINISTRATION"
              : "QUALITY STANDARDS"}
          </div>
          <nav aria-label="Quality standards">
            <Link
              href="/rubrics"
              className={pathname.startsWith("/rubrics") ? "active" : ""}
            >
              <BookOpen size={19} />
              Scorecards
            </Link>
            <Link
              href="/onboarding"
              className={pathname === "/onboarding" ? "active" : ""}
            >
              Setup guide
            </Link>
            {["OWNER", "ADMIN"].includes(session.user.role) && (
              <Link
                href="/team"
                className={pathname.startsWith("/team") ? "active" : ""}
              >
                Team &amp; Access
              </Link>
            )}
            {["OWNER", "ADMIN"].includes(session.user.role) && (
              <Link
                href="/flagged-terms"
                className={
                  pathname.startsWith("/flagged-terms") ? "active" : ""
                }
              >
                Flagged terms
              </Link>
            )}
            <Link href="/account">Account &amp; access</Link>
          </nav>
          <div className="sidebar-bottom">
            <Appearance />
            <div className="workspace-note">
              <ShieldCheck size={18} />
              <span>
                Operations workspace<small>Shared call quality review</small>
              </span>
            </div>
            <div className="user-row">
              <span className="avatar">
                {session.user.name.slice(0, 1).toUpperCase()}
              </span>
              <span className="user-info">
                <strong>{session.user.name}</strong>
                <small>{session.user.role.toLowerCase()}</small>
              </span>
              <button className="logout" onClick={logout} aria-label="Log out">
                <LogOut size={18} />
              </button>
            </div>
          </div>
        </aside>
        <div className="main-wrap">
          <header className="topbar">
            <span>
              Operations <span className="divider">/</span>{" "}
              <strong>
                {pathname.startsWith("/upload")
                  ? "Upload call"
                  : pathname.startsWith("/batches")
                    ? "Bulk upload"
                    : pathname.startsWith("/team")
                      ? "Team & Access"
                      : pathname.startsWith("/employees")
                        ? "Employees"
                        : pathname.startsWith("/onboarding")
                          ? "Setup guide"
                          : pathname.startsWith("/rubrics")
                            ? "Scorecards"
                            : pathname.startsWith("/calls")
                              ? "Calls / Audits"
                              : pathname.startsWith("/flagged-terms")
                                ? "Flagged terms"
                                : "Dashboard"}
              </strong>
            </span>
            <span className="workspace-tag">
              <Radio size={14} /> {session.user.organization_name}
            </span>
            <button
              className="mobile-logout icon-link"
              onClick={logout}
              aria-label="Log out"
            >
              <LogOut size={18} />
            </button>
          </header>
          <main className="main-content">
            {session.config.demo && (
              <div className="demo-banner">
                <span>DEMO MODE</span>Transcripts and QA are synthetic examples,
                not results from your recording.
              </div>
            )}
            {error && <ErrorBox message={error} />}
            {(!session.user.operational_access || !session.user.can_review) && (
              <BetaAccessNotice
                user={session.user}
                refresh={() => void refreshAccess()}
              />
            )}
            {pathname !== "/" &&
            (!session.user.organization_id ||
              session.user.organization_suspended ||
              !session.user.can_review ||
              ((pathname === "/upload" || pathname === "/batches") &&
                !session.user.operational_access)) ? (
              <p>
                Explore your dashboard or visit{" "}
                <Link href="/account">Account &amp; access</Link> for membership
                details.
              </p>
            ) : (
              children
            )}
          </main>
          <footer>
            Zoqari Signal{" "}
            <span>Quality intelligence for every interaction.</span>
          </footer>
        </div>
      </div>
    </Context.Provider>
  );
}
