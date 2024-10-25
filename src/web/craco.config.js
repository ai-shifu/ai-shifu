const cracoAlias = require("craco-alias");

module.exports = {
  plugins: [
    {
      plugin: cracoAlias,
      options: {
        baseUrl: "./src",
        source: "jsconfig",
      }
    }
  ],
  devServer: {
    client: {
      overlay: {
        errors: true,
        warnings: false,
        runtimeErrors: false, // 停止运行时错误的 overlay 提示
      }
    },
  },
  webpack: {
    configure: (webpackConfig) => {
      // 查找 Webpack rules 的 index
      const oneOfRuleIndex = webpackConfig.module.rules.findIndex(rule => rule.oneOf);

      if (oneOfRuleIndex >= 0) {
        // 为 Markdown 文件添加 raw-loader
        webpackConfig.module.rules[oneOfRuleIndex].oneOf.unshift({
          test: /\.md$/,
          use: 'raw-loader',
        });
      }

      return webpackConfig;
    },
  },
};
