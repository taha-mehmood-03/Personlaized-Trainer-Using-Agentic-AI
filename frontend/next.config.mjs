import bundleAnalyzer from '@next/bundle-analyzer'

const withBundleAnalyzer = bundleAnalyzer({
  enabled: process.env.ANALYZE === 'true',
  openAnalyzer: false,
})

/** @type {import('next').NextConfig} */
const nextConfig = {
  ...(process.env.NEXT_DIST_DIR ? { distDir: process.env.NEXT_DIST_DIR } : {}),
  // ESLint warnings (unused vars, unescaped quotes, etc.) are code-style issues,
  // not compile errors. Don't let them fail the production/Vercel build —
  // TypeScript type-checking below still runs and still blocks real type errors.
  eslint: {
    ignoreDuringBuilds: true,
  },
  compiler: {
    removeConsole: process.env.NODE_ENV === 'production' ? { exclude: ['error', 'warn'] } : false,
  },
  compress: true,
  images: {
    formats: ['image/avif', 'image/webp'],
  },
  poweredByHeader: false,
  reactStrictMode: true,
  experimental: {
    optimizePackageImports: ['lucide-react'],
    ...(process.env.NEXT_WEB_VITALS_DEBUG === 'true'
      ? { webVitalsAttribution: ['CLS', 'LCP'] }
      : {}),
  },
}

export default withBundleAnalyzer(nextConfig)
