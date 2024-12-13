const cracoAlias = require('craco-alias');

module.exports = {
  plugins: [
    {
      plugin: cracoAlias,
      options: {
        baseUrl: './src',
        source: 'jsconfig',
      },
    },
  ],
  devServer: {
    client: {
      overlay: {
        errors: true,
        warnings: false,
        runtimeErrors: false,
      },
    },
  },
  webpack: {
    configure: (webpackConfig) => {
      const oneOfRuleIndex = webpackConfig.module.rules.findIndex(
        (rule) => rule.oneOf
      );

      if (oneOfRuleIndex >= 0) {
        webpackConfig.module.rules[oneOfRuleIndex].oneOf.unshift({
          test: /\.md$/,
          use: 'raw-loader',
        });
      }

      // ios 16- don't support look behind
      webpackConfig.module.rules.push({
        test: /\.js$/,
        use: [{
          loader: 'string-replace-loader',
          options: {
            multiple: [
              {
                search: '?<=\\\\s|',
                replace: '',
              },
              {
                search: '?<=^',
                replace: '^',
              },
              {
                search: '?<="',
                replace: '?="',
              }
            ]
          }
        }]
      })


      if (process.env.NODE_ENV === 'production') {
        webpackConfig.devtool = false;
      }

      return webpackConfig;
    },
  },
};
