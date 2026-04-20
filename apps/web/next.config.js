/** @type {import('next').NextConfig} */
module.exports = {
  reactStrictMode: true,
  experimental: {
    serverActions: { bodySizeLimit: "100mb" }
  },
  webpack: (config) => {
    config.resolve.alias.canvas = false;
    return config;
  }
};
