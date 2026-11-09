import "./globals.css";

export const metadata = {
  title: "Varsha — Monsoon Onset & Break Outlook",
  description:
    "Probabilistic 1–4 week outlooks of monsoon onset, false onset, dry spells and heavy rain at block and panchayat level, with crop advisories in Telugu, Hindi and English.",
};

export const viewport = {
  width: "device-width",
  initialScale: 1,
  themeColor: "#0a0f1e",
};

export default function RootLayout({ children }) {
  return (
    <html lang="en">
      <head>
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="anonymous" />
        <link
          href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&family=Noto+Sans+Telugu:wght@400;600;700&family=Noto+Sans+Devanagari:wght@400;600;700&display=swap"
          rel="stylesheet"
        />
      </head>
      <body>{children}</body>
    </html>
  );
}
