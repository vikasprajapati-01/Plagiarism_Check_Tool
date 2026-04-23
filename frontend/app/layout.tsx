import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";
import { ThemeProvider } from "./components/ThemeProvider";

const inter = Inter({
  subsets: ["latin"],
  variable: "--font-inter",
  display: "swap",
});

export const metadata: Metadata = {
  title: "PlagiaCheck — AI-Powered Plagiarism Detection",
  description:
    "Samsung PRISM: Detect exact duplicates, fuzzy matches, semantic similarity, AI-generated content, web plagiarism, and license violations — all in one tool.",
  keywords: "plagiarism detection, exact duplicate, fuzzy matching, semantic similarity, AI content detection, license check",
  openGraph: {
    title: "PlagiaCheck — AI-Powered Plagiarism Detection",
    description: "Multi-method text plagiarism & duplicate detection tool.",
    type: "website",
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body className={`${inter.variable} min-h-screen flex flex-col`}>
        <ThemeProvider>{children}</ThemeProvider>
      </body>
    </html>
  );
}
