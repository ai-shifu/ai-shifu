
const getExtName =  (str: string) => str.slice(((str.lastIndexOf('.') - 1) >>> 0) + 2);

export default getExtName
