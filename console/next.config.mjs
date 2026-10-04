/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // Keep the development launcher from covering the mobile bottom navigation.
  devIndicators: false,
  // Next 16 默认会往仓库里生成 AGENTS.md / CLAUDE.md。这个仓库的 agent 约定写在
  // README 里，不要它自动生成。
  agentRules: false,
};

export default nextConfig;
