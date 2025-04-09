

find ./src -type f -name "*.tsx" -o -name "*.ts" | xargs sed -i 's/from '\''.*\.jsx'\''/from '\''\1'\''/' 

mkdir -p ./src/types
cat > ./src/types/declarations.d.ts << 'EOF'
declare module '*.scss';
declare module '*.css';
declare module '*.png';
declare module '*.jpg';
declare module '*.svg';
declare module '*.gif';
declare module '*.md';
declare module 'sse.js';
EOF

if [ ! -f ./tsconfig.json ]; then
  cat > ./tsconfig.json << 'EOF'
{
  "compilerOptions": {
    "target": "es5",
    "lib": ["dom", "dom.iterable", "esnext"],
    "allowJs": true,
    "skipLibCheck": true,
    "esModuleInterop": true,
    "allowSyntheticDefaultImports": true,
    "strict": false,
    "forceConsistentCasingInFileNames": true,
    "module": "esnext",
    "moduleResolution": "node",
    "resolveJsonModule": true,
    "isolatedModules": true,
    "noEmit": true,
    "jsx": "react-jsx",
    "baseUrl": "./src"
  },
  "include": ["src"],
  "exclude": ["node_modules"]
}
EOF
fi

if ! grep -q '"typescript":' package.json; then
  sed -i '/"dependencies": {/a\    "typescript": "^4.9.5",' package.json
fi

if ! grep -q '"@types/react":' package.json; then
  sed -i '/"dependencies": {/a\    "@types/react": "^18.0.0",' package.json
  sed -i '/"dependencies": {/a\    "@types/react-dom": "^18.0.0",' package.json
  sed -i '/"dependencies": {/a\    "@types/node": "^16.0.0",' package.json
fi

echo "TypeScript fixes applied successfully!"
