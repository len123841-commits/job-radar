# Job Radar

Job Radar 是一个“求职抓岗雷达”工具：从 LinkedIn、Indeed、Google Jobs、BOSS 直聘等平台抓取岗位，再结合你的简历、目标方向、城市和薪资要求，自动筛选、排序，并输出一份可直接投递的岗位清单。

它**只做抓取、筛选和汇总，不做自动投递**。设计目标很明确：帮你把“找岗位”这件事标准化、重复化、可配置化。

## 适合什么人

如果你属于下面这类场景，这个工具会比较合适：

- 你已经有明确的求职方向，想每天自动抓取符合条件的岗位
- 你希望按城市、薪资、岗位方向做筛选，而不是手动翻招聘网站
- 你想让工具根据最新简历自动调整排序与话术
- 你想要一份“今天可以直接去投”的岗位表，而不是一堆原始搜索结果

## 核心能力

- 多平台抓取：支持 `linkedin`、`indeed`、`google`、`zip_recruiter`、`glassdoor`，并可接入 `boss`
- 方向分层：支持把岗位方向分成 Tier 1 / Tier 2 / Tier 3
- 城市筛选：支持默认城市池，也支持临时覆盖
- 薪资过滤：支持设置月薪下限/上限
- 动态简历读取：优先使用你最近上传或指定的简历
- 智能排序：结合方向分层、关键词命中、城市、薪资做排序
- 投递辅助：生成一键投递备注、中文打招呼语、英文首句、cover letter 提示
- 多格式输出：同时输出 Markdown、CSV、JSON

## 输出长什么样

生成的岗位表默认会包含这些字段：

- 投递优先级
- 方向分层
- 平台
- 岗位
- 公司
- 投递链接
- 地点
- 薪资
- 发布时间
- 一键投递备注
- 中文打招呼语
- 英文首句
- cover letter 提示
- JD 摘要

其中“投递链接”已经前移到岗位和公司后面，方便直接点开投递。

## 项目结构

```text
job-radar/
├── README.md                      # 面向 GitHub 使用者的说明
├── SKILL.md                       # Skill 内部执行说明
├── assets/
│   └── default_profile.yaml       # 默认画像配置
├── scripts/
│   ├── ensure_deps.py             # 安装依赖与 BOSS 兼容修复
│   └── job_radar.py               # 主脚本：抓取、筛选、排序、输出
└── references/
    ├── profile-schema.md          # 配置字段说明
    └── usage-recipes.md           # 常用命令示例
```

## 快速开始

以下命令默认都在**仓库根目录**执行；如果你是从 GitHub clone 下来，进入 `job-radar/` 后直接运行即可。

### 1）安装依赖

```bash
python3 scripts/ensure_deps.py
```

如果你还要抓 BOSS 直聘，再执行：

```bash
python3 scripts/ensure_deps.py --with-boss
```

> `--with-boss` 会自动拉取上游 `boss-zhipin-scraper`，并补上 Python 3.9 兼容修复。

### 2）先看搜索计划

```bash
python3 scripts/job_radar.py plan --profile assets/default_profile.yaml
```

这一步不会联网抓取，只会把当前会使用的简历、关键词、城市、平台、薪资范围打印出来，方便你确认配置是否正确。

### 3）执行抓取

```bash
python3 scripts/job_radar.py search --profile assets/default_profile.yaml
```

运行后会输出 3 个文件路径：

- `job_radar_*.md`
- `job_radar_*.csv`
- `job_radar_*.json`

默认输出目录类似：

```text
job-radar-output/20260820_173000/
```

## 最重要的配置：怎么让它跑出你想要的岗位

这个工具的控制方式有两种：

- **长期默认设置**：改 `assets/default_profile.yaml`
- **一次性临时设置**：运行命令时传参数覆盖

如果你是自己长期使用，建议把常用方向、城市、薪资写进 YAML。  
如果你只是这一次想改，比如“今天只看北京”“这次只看 GTM 运营”，建议用命令行参数覆盖，不要直接改默认文件。

### 1）控制岗位方向

岗位方向主要由两个地方决定：

#### `candidate.search_terms`

这是**真正会拿去搜索平台的词**。比如：

```yaml
candidate:
  search_terms:
    - 海外运营
    - Global Campaign
    - Creator Growth
    - 社媒运营
    - 策略运营
```

如果你只想搜某几个方向，就改这里，或者运行时传：

```bash
python3 scripts/job_radar.py search \
  --profile assets/default_profile.yaml \
  --keywords "海外运营,社媒运营,策略运营"
```

#### `candidate.direction_pool`

这是**方向分层池**，用来决定排序层级，不一定全部直接拿去搜索。

```yaml
candidate:
  direction_pool:
    tier_1_strong:
      - 海外运营
      - Global Campaign
      - Creator Growth
    tier_2_potential:
      - 社媒运营
      - 内容运营
      - 用户增长运营
    tier_3_extended:
      - 策略运营
      - GTM运营
      - 流程优化
```

你可以这样理解：

- Tier 1：最想投、最贴简历的方向
- Tier 2：可以尝试的相关方向
- Tier 3：延展型岗位，作为补充池

如果你希望结果不只是一种岗位方向，就要把 Tier 2 / Tier 3 也补全，并且把你真的想搜的词放进 `search_terms` 或 `--keywords` 里。

### 2）控制城市

默认城市在这里：

```yaml
search:
  cities:
    - 北京
    - 上海
    - 深圳
    - remote
```

临时覆盖可以这样写：

```bash
python3 scripts/job_radar.py search \
  --profile assets/default_profile.yaml \
  --cities "北京,上海"
```

如果你只想看北京：

```bash
python3 scripts/job_radar.py search \
  --profile assets/default_profile.yaml \
  --cities "北京"
```

### 3）控制薪资下限

默认薪资范围在这里：

```yaml
search:
  min_monthly_salary_k: 15
  max_monthly_salary_k: 70
```

临时覆盖：

```bash
python3 scripts/job_radar.py search \
  --profile assets/default_profile.yaml \
  --min-salary-k 20 \
  --max-salary-k 40
```

含义是：对**可识别的月薪岗位**按 20K–40K 做过滤；如果平台返回的是未知薪资、时薪或日薪，脚本默认不会强行换算，你可以在结果里再做二次筛选。

### 4）控制简历来源

脚本每次抓取前都会自动找“最新简历”。默认会依次考虑：

- workspace 根目录
- `assets/`
- 当前运行目录

支持格式：

- HTML
- PDF
- DOCX
- Markdown
- TXT

如果你想强制使用某一份简历：

```bash
python3 scripts/job_radar.py search \
  --profile assets/default_profile.yaml \
  --resume-path "/path/to/your_resume.pdf"
```

这对于以下场景很有用：

- 你准备投另一类岗位，想换一版简历
- 你当天上传了多份简历，想指定其中一份
- 你在 CI 或定时任务里希望简历路径固定

## 常用命令示例

### 只跑 BOSS，抓北京岗位

```bash
python3 scripts/job_radar.py search \
  --profile assets/default_profile.yaml \
  --sites boss \
  --cities "北京"
```

### 跑 Tier 1 + Tier 2 的几个方向

```bash
python3 scripts/job_radar.py search \
  --profile assets/default_profile.yaml \
  --keywords "海外运营,主播运营,社媒运营,内容运营"
```

### 试水延展方向

```bash
python3 scripts/job_radar.py search \
  --profile assets/default_profile.yaml \
  --keywords "策略运营,GTM运营,流程优化"
```

### 只看近 3 天岗位

```bash
python3 scripts/job_radar.py search \
  --profile assets/default_profile.yaml \
  --hours-old 72
```

### 只输出前 50 个岗位

```bash
python3 scripts/job_radar.py search \
  --profile assets/default_profile.yaml \
  --top-n 50
```

### 第一次运行时自动拉取 BOSS 上游仓库

```bash
python3 scripts/job_radar.py search \
  --profile assets/default_profile.yaml \
  --sites boss \
  --bootstrap-boss
```

## 参数说明

下面这些参数最常用：

| 参数 | 作用 |
| --- | --- |
| `--profile` | 指定 YAML 配置文件 |
| `--resume-path` | 显式指定本次使用的简历路径 |
| `--keywords` | 临时覆盖搜索词，逗号分隔 |
| `--score-keywords` | 临时覆盖打分关键词 |
| `--cities` | 临时覆盖城市，逗号分隔 |
| `--sites` | 选择平台，如 `linkedin,indeed,google,boss` |
| `--min-salary-k` | 月薪下限，单位 K |
| `--max-salary-k` | 月薪上限，单位 K |
| `--hours-old` | 只保留最近 N 小时岗位 |
| `--results-per-search` | JobSpy 每组搜索抓多少结果 |
| `--boss-pages` | BOSS 每个关键词+城市抓几页 |
| `--top-n` | Markdown 里最多展示多少岗位 |
| `--remote-only` | 只保留 remote 岗位 |
| `--output-dir` | 指定输出目录 |
| `--boss-repo-path` | 指定本地 boss-zhipin-scraper 路径 |
| `--bootstrap-boss` | 缺少 BOSS 仓库时自动拉取 |

## 如果你是通过 AI 来用这个工具

如果不是直接跑命令，而是让 AI 帮你跑，建议把需求一次说清楚。最少带上这几类信息：

- 想投的方向：例如“海外运营 + 社媒运营 + 策略运营”
- 城市：例如“北京、上海，先不看深圳”
- 薪资：例如“最低 20K”
- 平台：例如“只看 BOSS”
- 时间窗口：例如“只看近 3 天”
- 简历：例如“用我刚上传的最新版简历”

一个更容易跑准的说法例子：

```text
帮我用最新版简历跑 job-radar，只看 BOSS，城市只要北京和上海，最低月薪 20K，方向覆盖 Tier 1 的海外运营、Tier 2 的社媒运营、Tier 3 的策略运营，输出前 50 个岗位。
```

这种描述方式会比“帮我看看有什么岗位”稳定很多。

## BOSS 使用说明

BOSS 直聘依赖本地浏览器登录态，和其他平台不一样。

你通常需要准备：

1. 本地 Chrome 已登录 BOSS
2. Chrome 开启远程调试端口（常见是 `9222`）
3. 运行 `python3 scripts/ensure_deps.py --with-boss`

如果环境没准备好，建议先跑 `linkedin/indeed/google`，不要被 BOSS 卡住整个流程。

## 推荐阅读

- [配置字段说明](references/profile-schema.md)
- [常用运行配方](references/usage-recipes.md)
- [Skill 说明](SKILL.md)

## License

MIT
