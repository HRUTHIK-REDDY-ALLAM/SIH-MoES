import "./globals.css";
import Footer from "./components/Footer";

export const metadata = {
  title: "Varsha — Monsoon Onset & Break Outlook",
  description:
    "Probabilistic 1–4 week outlooks of monsoon onset, false onset, dry spells and heavy rain at block and panchayat level, with crop advisories in Telugu, Hindi and English.",
};

export const viewport = {
  width: "device-width",
  initialScale: 1,
  themeColor: "#12355b",
};

export default function RootLayout({ children }) {
  return (
    <html lang="en">
      <head>
        {/* Stop Dark Reader from rewriting inline styles (causes hydration mismatches and breaks the portal theme). */}
        <meta name="darkreader-lock" />
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="anonymous" />
        <link
          href="https://fonts.googleapis.com/css2?family=Noto+Sans:wght@400;500;600;700;800&family=Noto+Sans+Telugu:wght@400;600;700&family=Noto+Sans+Devanagari:wght@400;600;700&display=swap"
          rel="stylesheet"
        />
      </head>
      <body>
        {children}
        <Footer />
      </body>
    </html>
  );
}
