import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "LifeFlow AI",
  description:
    "Quietly finds what needs attention, explains why it matters, and prepares the next step for your approval.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  // Browser extensions can add attributes to <html> and <body> before React
  // hydrates them (e.g. a password-manager or ad-blocker's own marker
  // attribute) — suppress the resulting mismatch warning on both root tags,
  // not just <body>.
  return (
    <html lang="en" className="h-full antialiased" suppressHydrationWarning>
      <body suppressHydrationWarning className="min-h-full flex flex-col">
        {children}
      </body>
    </html>
  );
}
