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
  // Browser extensions can add attributes to <body> before React hydrates it.
  return (
    <html lang="en" className="h-full antialiased">
      <body suppressHydrationWarning className="min-h-full flex flex-col">
        {children}
      </body>
    </html>
  );
}
