# 页面设计
## “日程”页面设计


## “文档”页面设计
### 概述
1. 用于浏览 markdown 文档的页面包含以下功能：
	1. 显示文档列表
		1. 文档列表支持树状层级显示（规划功能）
		2. 文档列表采用滚动加载功能
			3. 通过 [react-infinite-scroll-component](https://github.com/ankeetmaini/react-infinite-scroll-component) 组件实现
	2. 文档（指单个文件）检索功能
	3. 文档列表排序功能
		1. 时间正序排序
		2. 时间倒序序排序
		3. 名称正序排序
		4. 名称倒序排序
	4. markdown 文档查看功能
### 页面 url
1.  `/document`

# UI & 交互逻辑拆分
暂无设计图资料


# 状态
1. 文档列表
	1. 列表项添加 hover 状态
	2. 对应正在显示的文档要在列表中高亮显示 #待实现
	3. 文档列表 滚动加载时的 loading
	4. 顶部搜索栏在列表发生滚动时的吸顶状态
	5. 无数据时的状态
2. markdown 浏览器
	1. 无数据时 的状态
	2. loading时 的状态
