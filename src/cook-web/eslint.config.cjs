const { FlatCompat } = require('@eslint/eslintrc');

const compat = new FlatCompat({
  baseDirectory: __dirname,
});

const eslintConfig = [
  // Use Next.js recommended configuration (includes React, React Hooks, and Next.js rules)
  ...compat.extends('next/core-web-vitals', 'next/typescript', 'prettier'),
  {
    files: ['**/*.{js,jsx,ts,tsx}'],
    rules: {
      // Override specific rules as needed
      '@typescript-eslint/no-explicit-any': 'off',
      'no-console': 'warn', // Original was 'error', relaxed to 'warn'
      'next/no-img-element': 'off', // From original config
    },
  },
  {
    files: [
      '**/*.test.{js,jsx,ts,tsx}',
      '**/__tests__/**/*',
      '**/scripts/**/*.js',
      '**/jest.setup.js',
    ],
    rules: {
      'no-console': 'off', // Allow console in tests, scripts, and test setup
    },
  },
];

module.exports = eslintConfig;
