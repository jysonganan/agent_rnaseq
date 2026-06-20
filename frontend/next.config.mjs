/** @type {import('next').NextConfig} */
const nextConfig = {
  basePath: "/app",
  trailingSlash: true,
  ...(process.env.NEXT_EXPORT === "1" && { output: "export" }),
}

export default nextConfig
