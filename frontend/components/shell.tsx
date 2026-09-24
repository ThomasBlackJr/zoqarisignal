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
import { api, Account, Config, User } from "@/lib/api";
import { Appearance } from "./preferences";
import { Brand, ErrorBox, Loading } from "./ui";

const Context = createContext<{ user: User; config: Config } | null>(null);
export function useDrive() {
  const value = useContext(Context);
  if (!value) throw new Error("Missing Signal session");
  return value;
}
export function Shell({ children }: { children: React.ReactNode }) {
  const [session, setSession] = useState<{ user: User; config: Config } | null>(
    null,
  );
  const [error, setError] = useState("");
  const pathname = usePathname();
  const router = useRouter();
  useEffect(() => {
    let active = true;
    api<Account>("/account")
      .then(async (user) => {
        if (
          !user.email_verified ||
          !user.organization_id ||
          !user.operational_access ||
          !user.can_review
        ) {
          router.replace("/account");
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
          <nav>
            {[
              { href: "/", title: "Overview", Icon: LayoutDashboard },
              { href: "/calls", title: "Interactions", Icon: Headphones },
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
              <Link href="/team">Team &amp; Access</Link>
            )}
            {["OWNER", "ADMIN"].includes(session.user.role) && (
              <Link href="/flagged-terms">Flagged terms</Link>
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
                              ? "Interactions"
                              : "Overview"}
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
            {children}
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
