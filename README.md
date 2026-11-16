# 常青 · 企业学习留存队列

按首学周核对真实回访，在成熟观察周生成可追溯的干预名单。原生HTML/CSS/JS前端，Python真实计算，独立五服务Docker。

## 两套并存的计算方案

**点击方案（旧，保留）**：学习事件为单次点击，同周多事件只计1次回访。
**时段方案（新，冻结时段）**：导入带编号的学习起止时段（`code/learner/started_at/ended_at`），解决“一次点击就算回访、跨设备学习重复计学时”的问题：

- 按工号在Asia/Shanghai时间轴上做**并集合并**：重叠、相接时段只算一次，并保留全部来源时段编号作为合并依据。
- 合并区间按**ISO周一（周界）和每月1日（月界）拆分**，跨周、跨月的学习时间不重复计入。
- 单周合并学时**满30分钟才计回访**；该学员的队列周＝其**首次达标周**，不满30分钟的周不计回访（按未达标而非0人处理）。
- 每月每人**最多认定600分钟**（封顶），由月度结算账本认定；矩阵只展示原始合并学时。
- 提交时段方案即冻结当时全部时段快照与checksum；修订时段不改变旧矩阵，旧点击方案与旧数据完全保留。

## 真实业务与模块

模拟客户常青企业大学，运营组服务200名学员。原工作流从学习平台导出 `常青_学习事件_20261115.xlsx`，用工作簿手工找首学日期、统计每周回访，再复制缺席名单到周会纪要。三个痛点：同周多事件重复计人数、截断历史把老学员误算新客、未观察完整的周被当成零留存。上游是学习事件；本项目替代队列计算、成熟判断与成员核对；下游由学习负责人签核辅导安排。

四个业务模块：事件台账（录入/完整字段修订）、队列配置、留存矩阵（冻结版本/成熟遮罩/成员来源）、干预清单（站内草案/管理员签核/导出）。业务实体为Event、Cohort、Intervention，另有User和Audit。新增时段方案后扩展为六个界面：**时段台账**（编号起止时段、批量导入、合并依据）与**学时账本**（月度结算、入账分录、差额更正、结算作业）；新增实体StudySegment、LedgerMonth、LedgerEntry、LedgerCorrection、SettlementJob，Cohort以`scheme`区分click/segment。

|角色|权限与典型动作|
|---|---|
|admin|业务全部读写、审计、独占干预签核|
|analyst|事件录入修订、提交计算、起草清单、导出|
|viewer|业务只读与下载；后端禁止写入和计算提交|

## 启动与访问

```sh
cp .env.example .env
docker compose config --quiet
docker compose up -d --build
docker compose exec -T backend python -m scripts.seed_demo
```

前端 [localhost:18213](http://localhost:18213)，后端 [localhost:19213/docs](http://localhost:19213/docs)，MySQL宿主端口17713。演示邮箱 `admin@demo.local`、`analyst@demo.local`、`viewer@demo.local`，密码均 `Demo123!`。`SEED_DEMO=true`启动自动seed；自然键只插入缺失记录，不覆盖人工修订。种子包含200学员、2026-09-21起8个首学周、重复周内回访和截至日以后的未来事件；另含60名学员的272条带编号学习时段（含20条跨设备`-X`重叠时段），seed时即按工号重建待计算月份账。

## 一天的工作剧本

1. 08:50 viewer检查CQ-001到CQ-200的事件台账。
2. 09:00 analyst核对学习平台导出的事件唯一编号与上海本地时间。
3. 09:10 录入 `CQ-201-WEB`、学员CQ-201、2026-10-06 09:00、数据素养课程。
4. 09:20 如需修订，填记录ID和完整字段；同事件编号原内容重传不会新增。
5. 09:30 建“11月首学队列复核”：起周2026-09-21、止周2026-11-09、截至完整业务日2026-11-14、跟踪5周。
6. 09:40 worker计算，点击刷新；核对分母、W0到W5、未成熟遮罩。
7. 10:00 点击成熟列“查看未回访”，写“核对排班后安排站内学习辅导”，保存冻结成员。
8. 10:10 admin签核；10:20 viewer下载 `learning-cohort-<id>.json` 和 `learning-members-<id>.json`。

## 计算口径与边界

事件输入必须带时区；后端归一化UTC字符串，分周统一换算Asia/Shanghai。日期截至日表示已完整收集至上海本地日结束，包含该日全天；当日尚未结束时应选择上一完整业务日。演示默认截至2026-11-14；这是业务数据完整性约定，不自动探测采集watermark。未来事件从分析中排除并报告数量。ISO周从周一到周日，用周一日期作为队列键，跨年显示ISO年/周。

先扫描**所有截至日前历史**，每学员首学周=min(其事件周)，再按方案首学起止周过滤，不将窗口前老学员重新分配。第k周分母为首学队列唯一学员数，分子为该队列在目标周至少回访一次的唯一学员数；同周多事件只计1次。目标周周日≤截至日才成熟；成熟率=分子/分母，未成熟率保留null，成熟无回访为0。

提交时冻结所有事件、配置和checksum。修订原事件不会改变旧矩阵；需新建方案。无截至日前事件、窗口中无首学队列，任务置failed并说明。日期须为ISO周一且起周≤止周≤截至日；首学窗口最多一年，跟踪1–8周。事件同编号同内容重传返回原记录；同编号内容冲突409，需显式修订。数据库唯一键防重复。

干预清单只能选已成功方案、成熟非W0列且有未回访成员的单元格。成员由服务端从冻结结果生成，忽略客户端自报名单；未成熟/空清单409。签核后说明和名单不可覆盖。仅站内保留行动记录，不向学员外发消息。

## 月度结算账本（时段方案）

|状态|含义|
|---|---|
|pending 待计算|时段写入/修订后按工号自动重算的月份账，封顶后应认定分钟写入`computed_minutes`，未入账|
|posting 入账中|结算作业进行中（失败可重试）|
|posted 已入账|生成不可改写的结算分录，`recognized_minutes`＝结算分录＋更正分录之和|

口径与不变量：

1. **封顶**：每人每月原始合并学时超过600分钟按600认定，`capped`标记，差额不结转。
2. **已入账不改写**：posted月份的`recognized_minutes`与分录永不修改；其`last_known_minutes`只记录修订后的最新封顶总量作为依据留存。
3. **差额补记**：修订影响已入账月份时，差额＝修订后封顶总量 − 上次`last_known_minutes`（**按封顶后应认定总量计算**，非原始分钟），生成更正单补记到该工号**下一未结（pending）月份**；若日历下月已入账则继续顺延并自动开立未结月。原月依据保留，更正单在目标月结算时入账。
4. **幂等重试**：分录带自然唯一键`(learner,period,entry_type,ref_kind,ref_id)`，结算在单事务内完成；作业中断回滚后原样重试，已存在分录跳过，绝不重复记账。
5. **并发一致**：修订与结算都按工号对`ledger_months`加行锁（`SELECT … FOR UPDATE`，按learner+period定序），配合唯一键保证累计账实一致；单worker串行消费Redis队列，API在Redis不可用时退化为同事务内联结算。
6. 结算入口`POST /settlements`（可指定`period`或结算全部未结月），账本查询`GET /ledger/months|entries|corrections`、`GET /settlements`。

## 验证场景（源码外测试脚本，结论）

- **跨月重叠**：9-30 23:40→10-1 00:20 与 10-1 00:10→00:40 两设备时段并集为60分钟，按周界/月界拆为9月20、10月40（重叠10分钟只算一次）。
- **封顶后更正**：10月原始700按600入账后，下调到原始500，原月保留600，-100差额进11月；原始400上调到700，按封顶600产生+200（不是+300）。
- **入账中断重试**：结算写入中途抛错回滚，重试后一次入账、分录不重复；重复结算零新增。
- **并发修订与结算**：40个并发线程交错修订/结算后，零重复分录、各月分录合计恒等于认定量、已入账10月恒为600、更正单与更正分录1:1。

## 工程与本地开发

|部分|实现|
|---|---|
|后端|Python3.11、FastAPI、SQLAlchemy、PyJWT、PyMySQL|
|前端|原生ES modules、CSS、Nginx1.27|
|持久化|MySQL8、Redis7、命名产物卷|
|worker|Redis任务队列、DB状态、心跳文件、启动恢复queued/running|

目录：backend/src下routes/controllers/services/models/schemas/middlewares/config/utils/constants；frontend/src下api/stores/pages/components/common/hooks/utils/constants/types/router；backend/scripts/seed_demo.py；backend/migrations/001_initial.sql。所有计算/校验在Python，前端仅展示/交互。共有表格、表单字段、状态标签组件，form hook和HTML转义工具；请求ID与安全响应头两个中间件，写入业务审计和全局错误处理。

共享枚举：ROLES、STATES、COURSES、STAGES在后端src/constants/enums.py与前端src/constants/enums.js；schema/business.py约束课程与配置，models/entities.py存储状态。实例数据与队列名隔离；backend/worker依赖db和Redis健康，worker还等backend，frontend等backend。数据库、Redis和/artifacts均命名卷；五服务各有healthcheck。worker每轮刷新/tmp/heartbeat，结果在共享/artifacts。Nginx `/api/`去前缀代理到后端根路由。

环境变量见.env.example：COMPOSE_PROJECT_NAME、FRONTEND_PORT、BACKEND_PORT、DB_PORT、DB_PASSWORD、JWT_SECRET、SEED_DEMO、NETWORK_SUBNET。子网10.253.114.0/24规避本机默认地址池耗尽，移机可调整。部署时替换演示密码与JWT密钥。

本地开发可只起db/redis，backend安装requirements、设置DATABASE_URL/REDIS_URL/JWT_SECRET后 `uvicorn src.main:app --reload`；前端使用Nginx同源代理。ORM首次建表，初始MySQL DDL在migrations内；无在线版本迁移执行器。清理本项目：`docker compose down -v --remove-orphans`。

范围：点击方案保留逐条表单；时段方案支持单条与JSON批量导入（`POST /segments/import`，上限2000条/次），无删除或课程级独立留存；目前所有课程共同定义“学习回访/学时”。单worker、无外部学员通讯或生产学习平台连接，不宣称多worker exactly-once（结算幂等由数据库自然唯一键保证）。Google Fonts离线时回退serif/sans-serif。测试/截图在../../test-artifacts/gb-3114，源码不放证据。MIT许可证，见LICENSE。
