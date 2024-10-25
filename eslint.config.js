import babelParser from '@babel/eslint-parser';

export default [
  {
      files: ["**/*.js", "**/*.cjs", "**/*.mjs", "**/*.jsx", "**/*.ts", "**/*.tsx"], // 添加对 .ts 和 .tsx 文件的支持
      rules: {
          "prefer-const": "warn",
          "no-constant-binary-expression": "error"
      },
      languageOptions: {
        parser: babelParser,
        parserOptions: {
          requireConfigFile: false, // 禁用配置文件检查
          ecmaFeatures: {
            jsx: true,
          },
          babelOptions: {
            plugins: ["@babel/plugin-syntax-jsx"], // 启用 jsx 插件
          },
        },
      },
  }
];
