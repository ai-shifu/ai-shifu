import { shiNiangPlugin } from './ShiNiangPlugin';

// 确保只在客户端执行
if (typeof window !== 'undefined') {
  const plugins = window.shifuPlugins || [];
  plugins.push(shiNiangPlugin);
  window.shifuPlugins = plugins;
}

export { shiNiangPlugin };
