import type { Metadata } from "next";
import "./globals.css";
import "./workspaces.css";
import "./dokploy.css";
import "./source-workspace.css";

export const metadata: Metadata = {
  title: "JobPilot — Job Discovery Platform",
  description: "Intelligent job matching and application workspace.",
  robots: { index: false, follow: false }
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="pl"><body>{children}</body></html>;
}
