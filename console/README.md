# 求职控制台

本地求职系统的 Web UI。Next.js 16 App Router，只监听 `127.0.0.1:8788`。

## 它跟什么说话

只跟一个东西说话：`jobflowd`，本地 controller，在 `127.0.0.1:8791`。
控制台**不直接写求职仓库的文件**，也不碰 canonical state。数据都从 jobflowd 拿，
bearer token 只存在于服务端环境变量里，浏览器拿不到。

```
浏览器  ──▶  Next 路由 /api/*  ──▶  jobflowd  ──▶  仓库根目录（canonical state）
         同源                    bearer token
```

唯一的例外是 `api/opportunities`：它只读生成好的 `05-检索报告/岗位目录.json`，
仓库根目录取 `JOBFLOW_REPO`，没设就用 `console/` 的上一级。

## 跑起来

正常情况下不用手动跑——双击仓库根目录的 `打开本地求职控制台.command`，
或者运行 `00-工作流系统/local-control/start.sh`。它会启动 jobflowd、生成 token、
注入环境变量、再启动这里的 dev server。第一次运行前先在本目录 `npm install`。

**不要把仓库放进 iCloud / Dropbox 这类同步目录**：`node_modules` 和 `.next`
会被同步，产生冲突副本。

单独开发时：

```bash
npm install
npm run typecheck
npm run build
npm run dev        # 需要 JOBFLOWD_URL 和 JOBFLOWD_TOKEN
```

没有 token 的话页面会正常渲染，但每个面板都会显示"没读到"。

## 目录

```
app/
  layout.tsx              全局样式挂载点
  page.tsx                只负责渲染 <Console/>
  api/[resource]/route.ts 六个只读端点的统一代理；只有 runs 接受 POST
  api/document/route.ts   仓库里的 HTML / PDF / 截图代理
lib/
  types.ts                jobflowd 返回值的类型，这是跨仓库的唯一契约
  format.ts               日期、状态文案、状态色
  derive.ts               派生逻辑：逾期跟进、任务排序、run 树
  client.ts               浏览器侧取数
  server/jobflowd.ts      服务端代理与 token，只在服务端跑
components/
  console.tsx             外壳：导航、轮询、错误横幅
  primitives.tsx          Pill / Panel / Chips 这类小件
  views/*.tsx             六个页面，一个文件一个
styles/
  tokens.css              间距 8 档、字号 7 档、颜色语义。改数值只改这里
  base.css                重置与通用小件
  layout.css              外壳与响应式
  views.css               各页面
```

## 约定

- **不猜字段名。** `lib/types.ts` 按 jobflowd 的实际输出写死。渲染层出现
  `a ?? b ?? c` 式的兜底，说明契约变了，去改类型，不要在渲染层加分支。
- **只有 tokens.css 里有魔法数字。** 间距只用 `--s1`…`--s8`，字号只用 `--fs1`…`--fs7`。
- **深色写在 `:root`，浅色只做覆盖。** 有些内嵌预览会忽略 `prefers-color-scheme`。
- **不写营销文案。** 这是工作台，不是落地页；每一行都得是能看的数据。
- **写操作要同源检查。** 见 `lib/server/jobflowd.ts` 的 `sameOrigin`。
