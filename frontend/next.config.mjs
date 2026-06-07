/** @type {import('next').NextConfig} */
const nextConfig = {
  typescript: {
    // Prevents TypeScript errors from failing the Vercel production build
    ignoreBuildErrors: true,
  },
  eslint: {
    // Prevents ESLint errors from failing the Vercel production build
    ignoreDuringBuilds: true,
  },
};

export default nextConfig;
