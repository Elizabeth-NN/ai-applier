import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "AI Applier — Your AI Job Search Assistant",
  description:
    "Discover relevant jobs, tailor your resume, prepare applications, and manage your job search in one workspace.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
