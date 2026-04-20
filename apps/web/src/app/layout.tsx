import React from "react";
import "./globals.css";

export const metadata = {
  title: "Inzohra-ai",
  description: "Plan review, grounded.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="antialiased">{children}</body>
    </html>
  );
}
