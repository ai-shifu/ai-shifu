import { shiNiangPlugin } from './ShiNiangPlugin';

const plugins = window.shifuPlugins || [];
plugins.push(shiNiangPlugin);
window.shifuPlugins = plugins;

export { shiNiangPlugin };
