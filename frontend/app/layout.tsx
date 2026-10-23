import type { Metadata } from "next";
import Link from "next/link";
import "./globals.css";

export const metadata: Metadata = {
  title: "Cell Crime Scene",
  description: "Autonomous investigator for microscopy segmentation failures",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <header className="topbar">
          <Link href="/" className="brand">
            <span className="tape">CELL CRIME SCENE</span>
            <span className="brand-sub">segmentation investigator</span>
          </Link>
          <span className="disclaimer">Research image-analysis QC · not for clinical use</span>
        </header>
        <main className="container">{children}</main>
      </body>
    </html>
  );
}
