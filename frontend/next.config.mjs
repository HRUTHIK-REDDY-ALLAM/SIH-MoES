/** @type {import('next').NextConfig} */
const nextConfig = {
  // STATIC_EXPORT=1 npm run build -> plain HTML/JS in out/ for static hosting
  // (the app falls back to public/data/*.json when the API is unreachable).
  ...(process.env.STATIC_EXPORT === "1" ? { output: "export" } : {}),
};

export default nextConfig;
