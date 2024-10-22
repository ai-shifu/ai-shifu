
export default [
    {
        languageOptions: {
            ecmaVersion: 2022,
            sourceType: "module",
            globals: {
                myCustomGlobal: "readonly"
            }
        },
        rules: {
            semi: ["warn", "always"]
        }
    }
];
