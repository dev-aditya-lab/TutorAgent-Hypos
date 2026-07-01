import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Ai Tutor Agent - Your Personal Learning Companion",
  description: "An AI-powered tutor agent that helps students learn and understand various subjects through interactive conversations and personalized guidance.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html
      lang="en" >
      <body >{children}</body>
    </html>
  );
}
