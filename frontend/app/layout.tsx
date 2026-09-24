import { PreferenceProvider } from "@/components/preferences";
import type { Metadata } from "next";
import "@fontsource-variable/inter";
import "@fontsource-variable/sora";
import "./globals.css";
import "./signal.css";
import "./account.css";
import "./operations.css";
import "./appearance.css";

export const metadata: Metadata = {
  icons: { icon: "/brand/favicon.png", apple: "/brand/apple-touch-icon.png" },
  title: "Zoqari Signal · Quality intelligence",
  description: "Quality intelligence for every interaction.",
};
export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>
        <PreferenceProvider>{children}</PreferenceProvider>
      </body>
    </html>
  );
}
