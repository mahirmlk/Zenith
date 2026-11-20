/** @type {import('next').NextConfig} */
const PRODUCTION_BUILD_PHASE = 'phase-production-build';

module.exports = async (phase) => {
  if (phase === PRODUCTION_BUILD_PHASE) {
    const productionConfig = await import('./lib/production-config.js');
    productionConfig.default.validateProductionBuildEnvironment();
  }

  return {
    output: 'standalone',
    // Allow CI and local Windows verification to avoid ACL-protected build caches.
    distDir: process.env.NEXT_DIST_DIR || '.next',
    outputFileTracingRoot: __dirname,
    typedRoutes: true,
    async rewrites() {
      const apiUrl = process.env.NEXT_PUBLIC_API_URL;
      if (!apiUrl) {
        return [];
      }
      return [
        {
          source: '/api/:path*',
          destination: `${apiUrl}/api/:path*`,
        },
      ];
    },
  };
};
