
find src -name "*.ts" -o -name "*.tsx" | while read file; do
  sed -i "s/from ['\"]\\(.*\\)\\.js['\"]/from '\\1'/g" "$file"
  sed -i "s/import ['\"]\\(.*\\)\\.js['\"]/import '\\1'/g" "$file"
done
