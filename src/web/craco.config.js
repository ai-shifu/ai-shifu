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
  }
}
