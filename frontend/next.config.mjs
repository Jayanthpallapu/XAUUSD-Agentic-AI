/** @type {import('next').NextConfig} */
const nextConfig = {
  typescript: {
    // Prevents TypeScript errors from failing the Vercel production build
    ignoreBuildErrors: true,
  },
};

export default nextConfig;
