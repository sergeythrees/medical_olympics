import type { Metadata } from "next";
import Link from "next/link";

import "./globals.css";

export const metadata: Metadata = {
  title: "Medical Olympics — clinical cases",
  description: "Read the case, choose a diagnosis and management, get scored.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <header className="site-header">
          <Link href="/">Medical Olympics</Link>
        </header>
        <main>{children}</main>
      </body>
    </html>
  );
}
