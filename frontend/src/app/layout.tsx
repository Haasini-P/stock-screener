import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "StockMind AI — Institutional-Grade Stock Intelligence",
  description:
    "Real-time stock analytics platform with ML-powered predictions, explainability, and continuous learning. Analytical decision-support system for Indian equities.",
  keywords: [
    "stock analysis", "NSE", "BSE", "Indian stocks", "technical analysis",
    "machine learning", "predictions", "portfolio analytics", "market intelligence",
  ],
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className="dark">
      <head>
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="anonymous" />
      </head>
      <body className="antialiased min-h-screen">
        {children}
      </body>
    </html>
  );
}
