# 观市 A 股市场浏览看板

个人使用的沪深北 A 股盘后浏览工具：SW2021 一级行业展开二级行业、东方财富概念板块、龙头股（按 SW2021 行业指数权重前三筛选）、全部股票、全市场拼音搜索、自选与最近查看记录、数值排序、公司资料，以及前复权/不复权日周月 K 线、成交量、MACD 与 RSI 副图。

技术栈：Vue 3 / TypeScript / Element Plus / ECharts，FastAPI / SQLAlchemy / Alembic，SQLite。默认接入免费公开数据：AKShare 获取交易所名单、SW2021 行业与日历，东方财富行情不可用时使用腾讯。无需 Token；Tushare 保留为可选数据源。生产库不写入模拟行情。

## 安装

需要 Python 3.12 及以上、uv、满足 Vite 7 要求的 Node.js（20.19+ 或 22.12+）、npm。

```bash
uv sync --project backend --python 3.12 --locked
npm --prefix frontend ci
```

在项目根目录新建 `.env`，写入以下配置（如果已有该文件，只修改所需字段，不覆盖其他内容）：

```dotenv
DATA_PROVIDER=free
STOCK_DB_PATH=data/stock-panel.sqlite3
FREE_MIN_INTERVAL=0.35
# 仅选择 DATA_PROVIDER=tushare 时需要填写
TUSHARE_TOKEN=
```

.env 已被忽略。免费模式不需要注册 Tushare，也不自动购买任何权限。需要切换回原通道时，设置 `DATA_PROVIDER=tushare` 并配置 Token；同步命令也支持 `--provider tushare`，但日常自动同步使用 `.env` 的选择。

## 首次真实同步

以下命令均在仓库根目录执行：

```bash
backend/.venv/bin/python scripts/run.py doctor
backend/.venv/bin/python scripts/run.py bootstrap
```

`doctor` 只读预检；`bootstrap` 同步沪深北名单、31 个 SW2021 一级和 134 个二级行业、最新行情及 SW2021 行业指数成分权重，优先回填 100 只股票的近一年历史。免费源较慢，终端显示进度。

市场页左侧直接列出一级行业，展开某个一级行业可查看其二级子类；默认显示全部股票，列表右侧“龙头股”按钮可筛选当前层级的指数权重前三，所有范围共用同一张股票表。窄屏下拉框按相同层级分组。二级归属来自 SW2021 官方网站的个股分类历史文件，未找到官方归属的股票标记为“未细分”，不根据公司名称猜测。权重筛选读取 SW2021 行业指数公开成分的最新权重，先按源权重确定前三名，再核对当前上市状态和行业归属；缺失名次不递补；没有可用指数权重的分类不生成名单。指数权重排序是明确的数据口径，不是市占率、营收或投资评级。页面“数据详情”分别显示分类文件获取时间、来源最近变动日期和行情交易日。数据按盘后同步，不是逐笔实时行情；启动时及每日定时同步是否完成取决于上游可用性和本机运行状态。

左侧“行业 / 概念”切换浏览维度。概念目录和成分优先从通达信公开服务器的 `block_gn.dat` 批量获取，股票可属于多个概念；点击概念后仍用同一张股票表及搜索、市场、自选和排序筛选。达到源文件 400 只成分上限的板块不发布截断名单；已有东方财富有效名单时仍可浏览。“龙头股”筛选只在行业维度显示，概念概况不冒用 SW2021 行业指数。概念源与股票行情源分别同步，概念的“获取时间”不代表股票行情日期；上游失败时保留上次有效成分。

首次添加概念板块或需要单独刷新时运行 `PYTHONPATH=backend backend/.venv/bin/python -m app.cli sync-concepts`。常规 `sync` / `bootstrap` 也会在行情完成后尝试更新概念，概念源失败只会留下警告，不回滚有效行情。通达信接口为公开服务，若网络或服务不可用会保留上次有效名单。旧东方财富接口可用 `sync-concepts-em --concept 固态电池` 单独尝试，但不作为默认同步源。

新服务器不会随代码获得本机 `data/` 数据库。部署后先按上文运行 `bootstrap` 建立股票名单和行情，再运行 `sync-concepts` 并检查输出的 `updated`、`limited` 和网页中的概念计数。服务器需能向通达信公开行情节点发起出站 TCP 连接（通常为 7709 端口）；本机同步成功不代表服务器网络已验证。

个股详情和速览补充同一行情日期的流通市值、换手率、市盈率、市净率；详情还展示总股本和流通股本。免费模式从当前行情源读取这些字段，腾讯通道按源提供的股数展示；东方财富通道没有可核实的股本字段时留空。可选的 Tushare 通道从 [`daily_basic`](https://tushare.pro/document/2?doc_id=32) 获取对应指标，股本由万股换算为股，市值由万元换算为元。市盈率标签区分“动态”“TTM”和“行情源口径”，未获数据时显示“—”，不以市值和收盘价倒推。

顶部搜索可按代码、名称、拼音和首字母找全市场股票，不受当前筛选限制；列表内搜索仅过滤当前结果。股票表格默认展示全部股票，支持多字段服务端升降序；详情前后切换沿来源列表全量顺序，可跨分页。自选、最近查看和图表偏好保存在本机浏览器。

股票详情和速览按需获取历史：普通日线一年、周线至少五年、月线十年，图表可独立选择一个月至十年的显示区间，支持滚轮缩放、平移和重置。原始 OHLC 与复权 OHLC 独立保存；失败保留可用旧图和原基准并显示原因。MA、MACD、RSI 按所选周期计算，历史不足或未知缺口明确留空。正式停牌日跳过，不作缺失处理；免费数据源没有正式停牌解释。

市场概况显示当前行业/市场全体股票的涨跌家数和覆盖情况；选中行业按需读取同日官方指数，缺失明确提示，不使用股票平均涨幅代替。权重记录区分来源权重日期和本机获取日期。

旧版缺少原始 OHLC 的历史按需补齐；已缓存的多年历史不会被普通一年同步截短。长历史也可用 `backfill --codes 600519.SH --start 20161009 --end 20261009` 预取。Tushare 的长历史须按所需日期运行 backfill；旧日线缺开高低价或成交量时用 `--force` 重新同步。
免费快照允许少量明确标记的缺失，95% 以下有效覆盖会拒绝更新。缺失/无成交/日期不符的股票不参与涨跌榜，不能据此推断停牌。市值缺失显示空值。页面标注缺失数量和实际数据来源；这是免费模式的展示口径，与 Tushare 的严格逐日发布不同。

## 启动网页

开发模式：

```bash
backend/.venv/bin/python scripts/run.py dev
```

访问 http://127.0.0.1:5173 。API 在 http://127.0.0.1:8000 ，接口文档在 http://127.0.0.1:8000/docs 。

构建后运行：

```bash
npm --prefix frontend run build
backend/.venv/bin/python scripts/run.py serve
```

访问 http://127.0.0.1:8000 。应用只监听本机。启动命令在免费模式或已配置 Tushare 凭证时后台检查并补同步，网页不等待历史回填；退出启动命令会停止它启动的子进程。

## 线上实例（2026-10-13 首次部署）

访问地址：<https://guanshi.shop>，`https://www.guanshi.shop` 使用独立证书并跳转到主域名。

服务器为腾讯云 Ubuntu 26.04，沿用宝塔 Nginx 作为 HTTPS 入口。源码发布目录为 `/opt/stock-panel/releases/20261013-140313`，`/opt/stock-panel/current` 指向当前版本；Python 3.12 运行环境与系统 Python 分开。FastAPI 由 `stockpanel` 专用账号运行，仅监听 `127.0.0.1:8000`，同时提供 `frontend/dist` 和 `/api`。前端在本机构建，服务器无需运行 Vite。

- 数据库：`/var/lib/stock-panel/stock-panel.sqlite3`；环境配置：`/etc/stock-panel.env`。更新代码时保留这两个位置。
- 通达信测速缓存：`/var/lib/stock-panel/tdx-servers.json`，通过软链接供依赖包读写，避免给程序目录增加写权限。新建运行环境后运行 `deploy/configure-tdx-cache.py` 配置此链接。
- 网页服务：`stock-panel.service`，已配置开机启动和失败重启。
- 同步：`stock-panel-sync.timer`，北京时间每日 18:30，附加最多 60 秒随机延迟；进度由页面数据详情和服务日志展示。
- 备份：`stock-panel-backup.timer`，北京时间每日 03:30，一致性备份保存在 `/var/lib/stock-panel/backups/`，仅轮换本任务生成的备份，保留最近 14 份。这是同机备份，本次迁移前的本地副本位于 `deploy-artifacts/20261013-140313/`。
- `www` 证书：`stock-panel-cert-renew.timer` 每日两次检查，签发工具位于 `/opt/stock-panel/certbot-env/`；主域名继续使用宝塔原有证书，未被替换。
- 宝塔主站点配置：`/www/server/panel/vhost/nginx/guanshi.shop.conf`；`www` 跳转配置：同目录 `stock-panel-www.conf`。修改网站配置时保留代理和证书验证路径，不要给同一入口再添加重复的 `location /`。
- 部署前站点配置：`/var/backups/stock-panel/20261013-140313/guanshi.shop.conf`。首次部署失败时，可恢复此配置并通过 Nginx 检查后重载，网页会回到原宝塔占位页；不删除数据库。

以下命令在服务器执行：

```bash
# 查看状态与最近日志
sudo systemctl status stock-panel --no-pager
sudo journalctl -u stock-panel -n 80 --no-pager
sudo journalctl -u stock-panel-sync -n 80 --no-pager
sudo systemctl list-timers 'stock-panel-*' --no-pager

# 手动同步、备份、重启网页
sudo systemctl start --no-block stock-panel-sync
sudo systemctl start stock-panel-backup
sudo systemctl restart stock-panel

# 只读健康检查
curl -f http://127.0.0.1:8000/api/data-status
```

`deploy/bootstrap-server.sh`、`configure-nginx.py`、`configure-www-https.sh` 和 `configure-tdx-cache.py` 记录首次安装步骤，包含首次发布编号，已有实例不要直接重跑。日常更新使用下方的 `deploy/update.sh`。

首次上线验证：前端生产构建、70 项后端测试、8 项前端单元测试通过；公网首页、个股详情深链接、K 线周期切换、概念筛选与手机宽度展示已检查，应用服务重启后健康接口正常，数据库备份完整性与 `www` 证书续期演练通过。没有重启整台服务器。2026-10-13 14:14 的手动全量同步完成了名单和行业更新，但目标盘后日期为 20261012，上游已返回 20261013 盘中行情，快照日期校验拒绝发布并保留旧行情；该轮任务如实记录为失败。独立云端检查确认腾讯行情、原始/复权历史及通达信 269 个概念文件可读取；18:30 的完整盘后同步尚待实际触发，不把连接测试当作发布成功。

## 一键更新线上代码

在**本机项目目录**运行，默认目标为 `ubuntu@43.129.204.116`、SSH 端口 22、网站 `https://guanshi.shop`：

```bash
cd /Users/xingchen/前端/个人项目/stock-panel
./deploy/update.sh
```

本机需已安装 Python 3.12+、uv、Node.js/npm 和 OpenSSH。脚本使用 SSH 已配置的密钥；使用密码登录时，在终端按提示输入一次服务器密码，同一次发布会复用连接，不保存密码。首次连接新主机需核对 SSH 主机指纹。服务器需允许 `ubuntu` 执行免密 sudo（首次部署时已验证）。先前的临时部署密钥已撤销，不会被脚本复用。

可选命令：

```bash
# 只检查登录、sudo 和现有服务，不更新线上
./deploy/update.sh --check

# 只运行测试、生产构建和打包，不连接服务器
./deploy/update.sh --prepare-only

# 已配置自己的部署密钥时使用（请替换为实际路径）
./deploy/update.sh --identity "$HOME/.ssh/guanshi_deploy"

# 也支持 SSH 别名或自定义端口，仍要求服务器采用本项目现有目录与服务配置
./deploy/update.sh --host guanshi --port 22
```

脚本先运行部署保护测试，安装锁定依赖，执行后端测试、前端单元测试及生产构建，再生成 `deploy-artifacts/<发布编号>/app.tar.gz` 与 SHA256 清单。只打包程序、配置模板和前端产物，不上传本机 `.env`、数据库、虚拟环境或 SSH 密钥。

服务器会校验上传包，在独立 release 中安装依赖、配置通达信可写缓存，并确认迁移文件及数据库版本未变化。依赖安装期间旧站继续服务；若行情同步仍在进行，会保留旧站并退出，等待同步结束后重新运行即可。切换阶段会暂停原本启用的同步定时器并持有同步锁，生成一致性数据库备份，切换 `current`、重启应用，验证首页、静态资源和 `/api/data-status`，最后恢复定时器。服务重启期间有短暂不可用。

本机最后会核对公网 HTTPS 首页版本及 API。服务器更新由独立 systemd 任务运行，SSH 中断不会直接终止发布；中断后先按输出的发布编号查日志，确认结果后再决定是否重新运行：

```bash
# 以下命令在服务器执行，将 <发布编号> 替换为脚本输出值
sudo systemctl status stock-panel-update-<发布编号> --no-pager
sudo tail -n 80 /var/log/stock-panel-update-<发布编号>.log
readlink -f /opt/stock-panel/current
```

失败与回退规则：

- 构建、依赖安装、校验或备份失败时，不切换线上版本。切换后的服务启动或服务器健康检查失败时，自动切回上一版并再次检查；数据库不会被旧备份覆盖。回退本身失败会报错，必须检查发布日志和网站服务状态。
- 公网验证失败会明确报错，但不会因本机网络故障自动回退已通过服务器检查的新版本。
- 新增、删除或修改 `backend/migrations/*.py`（含子目录）、`backend/alembic.ini` 或 `backend/app/db.py` 会停止快速更新。这类更新需单独安排数据库迁移及恢复方案；脚本没有跳过此保护的参数。
- 保留 `/var/lib/stock-panel/stock-panel.sqlite3`、`/etc/stock-panel.env`、Nginx 与证书配置。不要把本机数据库重新上传覆盖线上数据。
- 更新前备份为 `/var/lib/stock-panel/backups/before-update-<发布编号>.sqlite3`，与日常 14 份轮换备份分开保留。旧 release、失败的候选 release、上传包和发布日志不自动删除；定期确认稳定版本与备份后再清理，空间不足时脚本会停止更新。

部署保护测试可独立运行：`python3 -m unittest discover -s deploy/tests -v`。这些测试使用临时目录和模拟服务命令验证失败恢复，不连接或重启线上服务器。

## 日常数据操作

```bash
# 更新当前名单、行业、最新行情，并处理 20 只待回填股票
backend/.venv/bin/python scripts/run.py sync

# 后台全市场近一年历史：顺序限速，可能耗时数小时，可中断后重跑
backend/.venv/bin/python scripts/run.py backfill

# 一次只处理 200 只，或只补指定股票；已完成的股票跳过
backend/.venv/bin/python scripts/run.py backfill --history-limit 200
backend/.venv/bin/python scripts/run.py backfill --codes 600519.SH,000001.SZ,920000.BJ

# 重新抓取指定股票，修复已知历史缺口
backend/.venv/bin/python scripts/run.py backfill --codes 600519.SH --force

# 仅更新最新行情，不回填历史
backend/.venv/bin/python scripts/run.py sync --history-limit 0

# 单独刷新 SW2021 行业指数指数权重前三（不会改动行情快照）
backend/.venv/bin/python scripts/run.py sync-leaders

# 使用 SQLite 一致性备份，不覆盖已存在的备份文件
backend/.venv/bin/python scripts/run.py backup --output data/backups/market-20261009.sqlite3
```

更多数据规则及任务安装方式见 [数据同步说明](docs/数据同步说明.md)。

## 验证

```bash
backend/.venv/bin/python -m pytest backend/tests -q
backend/.venv/bin/ruff check backend scripts
npm --prefix frontend run build
npm --prefix frontend run test:unit
# 首次使用 Playwright 的浏览器时
cd frontend
npx playwright install chromium
npm run test:e2e
```

本机已安装 Google Chrome 时，也可在仓库根目录运行：

```bash
PLAYWRIGHT_CHANNEL=chrome npm --prefix frontend run test:e2e
```

浏览器测试自动启动 8011 端口的隔离服务，使用新建的临时 SQLite 数据库。测试中的公司名称和行情均为合成夹具，不会写入日常数据库。

## 文档

- [第一版需求文档](docs/第一版需求文档.md)
- [数据同步说明](docs/数据同步说明.md)
- [验收记录](docs/验收记录.md)
- [旧一级代表股配置（已停用）](config/representatives.json)
- [旧二级代表股配置（已停用）](config/representatives_l2.json)

旧人工配置仅保留为历史核对资料，不再由日常同步或网页读取。指数权重前三由公开指数成分权重生成，来源链接、权重日期（源未提供时明确留空）和获取日期随每只股票展示。
