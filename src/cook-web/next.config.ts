import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  /* config options here */
  async redirects() {
    return [
      {
        source: '/',         // 源路径
        destination: '/main', // 目标路径
        permanent: true,     // 设置为 true 表示永久重定向（返回 308 状态码），否则为临时重定向（307 状态码）
      },
    ];
  },
};

export default nextConfig;
