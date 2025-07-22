// 测试 pre-commit.ci 自动格式化
const messy = 'code';
const data = { x: 1, y: 2, z: 3 };

function badFormatting() {
  console.log('this should be formatted');
  return true;
}

export default { messy, data, badFormatting };
