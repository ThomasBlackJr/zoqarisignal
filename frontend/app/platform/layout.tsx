import { cookies } from "next/headers";
import { redirect } from "next/navigation";
import { PlatformShell } from "@/components/platform";
import "./platform.css";

export const dynamic = "force-dynamic";

export default async function PlatformLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const cookie = (await cookies()).get("drive_session");
  if (!cookie) redirect("/login");
  let response: Response;
  try {
    response = await fetch(
      `${process.env.BACKEND_URL || "http://127.0.0.1:8000"}/platform/session`,
      {
        cache: "no-store",
        headers: { Cookie: `drive_session=${cookie.value}` },
        signal: AbortSignal.timeout(10000),
      },
    );
  } catch {
    return (
      <main className="empty" role="alert">
        Zoqari Admin is temporarily unavailable. Please try again.
      </main>
    );
  }
  if (response.status === 401) redirect("/login");
  if (response.status === 403) redirect("/account");
  if (!response.ok)
    return (
      <main className="empty" role="alert">
        Zoqari Admin is temporarily unavailable. Please try again.
      </main>
    );
  const user = await response.json();
  if (user.is_platform_admin !== true) redirect("/account");
  return <PlatformShell name={user.name}>{children}</PlatformShell>;
}
