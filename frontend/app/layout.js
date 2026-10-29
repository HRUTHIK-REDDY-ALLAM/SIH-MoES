import "./globals.css";

export const metadata = {
  title: "Varsha — Monsoon Intelligence System",
  description:
    "Probabilistic monsoon forecasting and crop advisory system for Indian farmers at block and panchayat level.",
};

export default function RootLayout({ children }) {
  return (
    <html lang="en">
      <head>
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link
          rel="preconnect"
          href="https://fonts.gstatic.com"
          crossOrigin="anonymous"
        />
        <link
          href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&display=swap"
          rel="stylesheet"
        />
        <meta name="theme-color" content="#0a0f1e" />
        <meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1" />
      </head>
      <body>
        <div id="app-root">{children}</div>
      </body>
    </html>
  );
}
