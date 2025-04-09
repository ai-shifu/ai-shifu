
find ./src -name "*.js" -not -path "*/node_modules/*" | while read file; do
  if [[ ! "$file" == *".d.js" ]]; then
    mv "$file" "${file%.js}.ts"
  fi
done

find ./src -name "*.jsx" -not -path "*/node_modules/*" | while read file; do
  mv "$file" "${file%.jsx}.tsx"
done
