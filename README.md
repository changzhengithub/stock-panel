# 观市 A 股市场浏览看板

个人使用的沪深北 A 股当日行情与历史浏览工具：SW2021 一级行业展开二级行业、东方财富概念板块、龙头股（按 SW2021 行业指数权重前三筛选）、全部股票、全市场拼音搜索、自选与最近查看记录、数值排序、公司资料，以及前复权/不复权日周月 K 线、成交量、MACD 与 RSI 副图。

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


## 免费当日行情

网页服务启动后自动从腾讯公开行情批量获取沪深北全部当前上市股票，腾讯失败或某一市场有效覆盖低于 95% 时尝试东方财富全市场接口。无需注册、Token 或付费实时权限。每条报价保留来源交易日期和时分秒，不把获取时间当作成交时间，不把上一交易日改成当天。

服务在北京时间 09:15～16:10 每轮完成后间隔 120 秒更新整批报价，其他时段间隔 15 分钟更新；浏览器可见时每 30 秒刷新列表、详情和 K 线，重新切回页面立即刷新。自动更新保持表格与统计可见，只替换变化的数据，不显示变淡动画或加载占位；保留滚动、选中股票及 K 线缩放，数据相同时不重绘图表。免费源延迟以实际返回时间为准。涨跌幅、最新价、市值、成交额和换手率排序按全量筛选结果计算后再分页，涨跌家数使用相同批次；个股提供昨收、今开、最高、最低、成交量（手）、成交额、市值、换手率、PE/PB 和股本，来源缺失的字段留空。

当日行情单独原子写入数据库旁的 `<数据库文件名>.realtime.json`，例如 `data/stock-panel.realtime.json`。不改写盘后发布记录、历史 K 线或复权因子，不需要数据库迁移。失败保留上次有效批次并在页面显示异常和原始日期；某股当日缺失时留空，不用昨日报价填充当前批次。当前股票池的 ST、退市过滤继续生效，新行情名称中的 ST 标记也应用于浏览入口。

当天 K 线使用免费源的开高低收和成交量；前复权图只有在缓存的上一交易日价格与来源昨收一致时才拼接，复权基准尚未确认时明确提示。盘后任务仍负责历史和复权数据。行业官方指数有独立来源和日期，缺少同日指数时显示暂无，不用股票平均值替代。

手动获取一轮当日行情并报告三个市场覆盖率：

```bash
backend/.venv/bin/python scripts/run.py refresh-quotes
```

服务账号需要能写数据库所在目录，并能访问腾讯／东方财富 HTTPS 接口。`REALTIME_QUOTES=0` 仅用于隔离或离线测试；默认开启。该改动随正常代码更新发布，已有线上实例在发布前仍使用原版本。

## 热门板块资金

主导航“热门板块”进入 `/hot-sectors`，提供东方财富行业/概念今日、5日、10日资金排行、完整板块搜索、流入/流出筛选、每日资金趋势、当日拆分和同源成分股资金。桌面排行与详情并列，手机点击进入板块详情；进入个股后可返回原排行条件。

默认免费、无 Token，`FUND_FLOW_ENABLED=1` 随网页服务独立采集；设为 0 可关闭自动任务。排行和成分资金缓存约五分钟刷新，历史三十分钟按需取数；页面三十秒读缓存。来源时间、获取时间、失败和缺失明确展示，失败保留旧数据。板块采用资金源分类，和市场页 SW2021/通达信不按同名合并；总额保留源完整口径，个股列表按本站规则过滤。

```bash
backend/.venv/bin/python scripts/run.py doctor-fund-flow
backend/.venv/bin/python scripts/run.py sync-fund-flow
backend/.venv/bin/python scripts/run.py sync-fund-flow --fund-board EM-concept-BK1136
```

已有数据库升级前运行 `backup` 保存新的备份文件，再运行 `migrate`（新增 0010）。本次本机备份为 `data/backups/before-fund-flow-20261013.sqlite3`，完整性检查通过。当前日历史不宣称最终完成；来源未提供的5日/10日起点不推算。本功能本机已验收，尚未发布到线上实例。

## 首次真实同步

以下命令均在仓库根目录执行：

```bash
backend/.venv/bin/python scripts/run.py doctor
backend/.venv/bin/python scripts/run.py bootstrap
```

`doctor` 只读预检；`bootstrap` 同步沪深北名单、31 个 SW2021 一级和 134 个二级行业、最新行情及 SW2021 行业指数成分权重，优先回填 100 只股票的近一年历史。免费源较慢，终端显示进度。

市场页左侧直接列出一级行业，展开某个一级行业可查看其二级子类；默认显示全部股票，列表右侧“龙头股”按钮可筛选当前层级的指数权重前三，所有范围共用同一张股票表。窄屏下拉框按相同层级分组。二级归属来自 SW2021 官方网站的个股分类历史文件，未找到官方归属的股票标记为“未细分”，不根据公司名称猜测。权重筛选读取 SW2021 行业指数公开成分的最新权重，先按源权重确定前三名，再核对当前上市状态和行业归属；缺失名次不递补；没有可用指数权重的分类不生成名单。指数权重排序是明确的数据口径，不是市占率、营收或投资评级。页面“数据详情”分别显示分类文件获取时间、来源最近变动日期和行情交易日。股票基础报价由网页服务自动获取当天免费行情，列表、详情和涨跌统计共用同一份行情缓存；页面显示来源时间。历史日线、行业归属及权重仍按各自任务更新。

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

# 本次包含新增数据库迁移时，先演练再停服迁移、更新
./deploy/update.sh --migrate

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
- 默认模式遇到数据库迁移变更会停止并列出具体文件。包含新增迁移的发布使用 `./deploy/update.sh --migrate`，不会跳过备份或校验；已部署的迁移历史、`backend/alembic.ini` 与 `backend/app/db.py` 仍不允许重写。允许新增迁移文件及调整 `migrations/env.py` 中的模型注册。
- 保留 `/var/lib/stock-panel/stock-panel.sqlite3`、`/etc/stock-panel.env`、Nginx 与证书配置。不要把本机数据库重新上传覆盖线上数据。
- 更新前备份为 `/var/lib/stock-panel/backups/before-update-<发布编号>.sqlite3`，与日常 14 份轮换备份分开保留。旧 release、失败的候选 release、上传包和发布日志不自动删除；定期确认稳定版本与备份后再清理，空间不足时脚本会停止更新。

部署保护测试可独立运行：`python3 -m unittest discover -s deploy/tests -v`。这些测试使用临时目录和模拟服务命令验证失败恢复，不连接或重启线上服务器。

### 包含数据库迁移的更新

例如从首次部署的 `0009` 升级到资金流、产业链等功能所需的 `0014`，应在本机运行 `./deploy/update.sh --migrate`。默认命令不会自动执行这些迁移；遇到迁移保护报错表示尚未切换线上版本，无需删除失败目录或重新上传本地数据库。

迁移模式先确认正式库与旧版代码一致、迁移链可向前升级，然后在服务器创建正式库的一致性副本，使用新版本运行环境演练 Alembic 升级，检查目标版本、SQLite 完整性和外键。演练失败时旧站继续运行。演练副本用完自动清理。

演练通过后，暂停同步定时器并获取同步锁，停止网站及其后台采集线程，再生成最终备份。随后以 `stockpanel` 用户执行正式迁移，验证数据库后切换代码并启动网站；服务器健康检查通过才恢复同步定时器。迁移模式停服时间包含正式备份、迁移及启动检查。

**正式迁移阶段失败会保持网站和同步定时器停止，保留数据库与备份，不自动覆盖数据库或重启旧代码。** 旧代码可能无法识别新的 Alembic 版本，而新服务启动后可能已有写入，不能直接恢复旧备份丢弃数据。查看发布日志及候选版本目录中的 `migration-state.json`，其中记录旧版路径、候选版本、正式库、备份和最后阶段。恢复时先保留失败现场（包括 SQLite WAL 文件），核对实际迁移进度与备份完整性，再决定修复新版本继续启动还是进行人工数据恢复；不要直接切换 `current` 或重跑首次安装脚本。更新期间不要另外手动启动同步或迁移命令。

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
- [热门板块开发计划](docs/热门板块开发计划.md)
- [旧一级代表股配置（已停用）](config/representatives.json)
- [旧二级代表股配置（已停用）](config/representatives_l2.json)

旧人工配置仅保留为历史核对资料，不再由日常同步或网页读取。指数权重前三由公开指数成分权重生成，来源链接、权重日期（源未提供时明确留空）和获取日期随每只股票展示。


## 产业链分析

本地入口：[产业链分析](http://127.0.0.1:8000/industry-chains)。包含动力电池、光伏、半导体三条公开资料专题，以及 31 个一级、134 个二级行业基线；所有行业分别解释投入、需求、经营量价、现金风险和竞争维度；公司业务关联与分部财务也提供解读，核验状态逐项标注。支持图谱与关系解释、节点公司/龙头依据、同节点比较、本地收藏、个股返回。资料缺失明确留空，未覆盖行业不会生成未经核验的结论。

内容位于 `config/industry_chains/`。首次在另一数据库使用时，先通过既有 `backup` 命令保存一致性备份，随后逐条执行校验、导入、资料核验记录与发布。核验人和说明填写实际情况，不将自动校验等同证据审阅：

```bash
backend/.venv/bin/python scripts/run.py validate-chain --chain-file config/industry_chains/power-battery.json
backend/.venv/bin/python scripts/run.py import-chain --chain-file config/industry_chains/power-battery.json
# 使用导入返回的版本 ID，记录实际核验人和具体说明
backend/.venv/bin/python scripts/run.py review-chain --chain-revision '替换为导入返回的版本ID' --chain-reviewer '实际核验人' --chain-review-note '已核对的资料、定位、判断与仍存在的缺口'
backend/.venv/bin/python scripts/run.py publish-chain --chain-revision '替换为导入返回的版本ID'
backend/.venv/bin/python scripts/run.py doctor-chain
```

光伏、半导体分别使用 `photovoltaic.json`、`semiconductor.json`。`validate-chain` 不执行迁移或发布；导入并不改变公开版本，发布必须先登记核验。修订文件重新导入会建立新版本，已发布版本不可原地改写。迁移为 0011，不清理旧行情或历史；手工专题内容不在启动时自动发布；全行业自动更新使用独立校验流程。

全行业基线可用以下命令采集、生成和发布；采集后只生成待校验版本，发布要记录实际核验范围。公开汇总资料不自动升级为原始公告核验。

```bash
backend/.venv/bin/python scripts/run.py collect-business
# 环境代理不可用时可指定 --direct-network；--force 重新抓取当前批缓存
backend/.venv/bin/python scripts/run.py build-industry-chains
backend/.venv/bin/python scripts/run.py publish-chain-batch --chain-file data/industry-chain-drafts/manifest.json --chain-reviewer '实际核验人' --chain-review-note '说明实际校验和补证范围，明确业务词关联及数据商财务的待核验部分'
```

框架位于 `config/industry_models/`；全行业覆盖与来源缺口见 [全行业数据验收](docs/全行业产业链数据验收.json)。不需要模型 Token，启动会调度全行业公开业务资料采集。0012/0013/0014 迁移保留原行情与证券数据。

本机内容已导入。开发/验收状态见 [产业链分析开发计划](docs/产业链分析开发计划.md) 与 [数据验收](docs/产业链数据验收.json)。AI 草稿、情景推演与事件跟踪为后续阶段，本次未接入模型服务。


### 产业分析自动更新

服务运行时默认启用：首次启动检查全行业资料，之后每 24 小时重新采集；失败后 1 小时重试，进程重启会恢复检查。`CHAIN_AUTO_UPDATE=0` 关闭调度，`CHAIN_UPDATE_INTERVAL_HOURS` 调整间隔，`CHAIN_UPDATE_DIRECT_NETWORK=1` 使用直连。任务有跨进程文件锁，采集不占数据库写事务。

自动流程为：刷新免费公开接口 → 分页与覆盖校验 → 对比有效业务、财务、股票池和规则 → 无变化跳过构建；有变化则重建全部行业 → 校验全部专属分析 → 在一个事务中切换全行业发布指针。95% 主营覆盖、90% 财务覆盖以及同报告期覆盖退化检查不通过时保留上一批快照；任何构建或发布失败保留已发布分析。数据商资料仍逐项标记待原始公告核验，自动校验不会冒充人工审核。

报告期包括已过常规披露截止时间的 FY/H1 和刚结束的 FY/H1，允许提前披露的最新资料进入采集；尚未披露、季度报表和缺失分部仍不冒称完整。行情按原有独立机制刷新。

页面默认跟随最新分析，每 30 秒检查版本；节点、筛选、分页和滚动保持。点击“固定当前版本”或打开带 `revision` 的历史链接才固定正文；点击“跟随最新分析”恢复自动切换。比较页面固定用户选择时的版本，避免比较途中口径变化。

`config/industry_models/maintenance.json` 登记经营规则维护日及 90 天复核周期。每 7 天检查龙头引用来源的可访问性和内容 hash；历史报告期、来源变化或不可访问生成复核清单并在公司依据中提示。下载成功、文件未变、行情刷新均不表示事实或行业规则已重新核验。调整经营规则/补充证据后，调度在下一次检查识别变化并重建。

```bash
# 强制立即执行全行业采集、校验和自动发布（失败返回非零）
PYTHONPATH=backend backend/.venv/bin/python -m app.cli update-industry-chains --force --direct-network
# 查看最近结果、下次检查、错误和证据维护清单
PYTHONPATH=backend backend/.venv/bin/python -m app.cli doctor-chain-updates
```

公开只读接口：`GET /api/industry-chains/update-status`、`GET /api/industry-chains/{id}/version`；不开放公网触发采集或发布的写接口。0014 迁移新增任务审计表，失败与成功时间分别保存。
