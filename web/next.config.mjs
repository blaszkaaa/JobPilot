/** @type {import('next').NextConfig} */
const nextConfig = {
  output: 'standalone',
  async rewrites() {
    return [{ source: '/api/:path*', destination: 'http://jobpilot-internal-api:8000/api/:path*' }];
  },
};
export default nextConfig;
