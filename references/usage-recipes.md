# 使用说明与运行配方

这份文档偏“拿来就跑”。如果你是第一次接触 Job Radar，建议先看根目录的 `README.md`；如果你已经知道自己要改哪些条件，直接从下面复制命令就行。

## 推荐工作流

### 1. 首次使用：安装依赖

```bash
cd user_skills/job-radar
python3 scripts/ensure_deps.py
```

如果要抓 BOSS 直聘，再执行：

```bash
python3 scripts/ensure_deps.py --with-boss
```

## 2. 先看搜索计划

```bash
cd user_skills/job-radar
python3 scripts/job_radar.py plan --profile assets/default_profile.yaml
```

这个步骤不会联网抓取，只会预览：

- 当前会用哪份简历
- 搜索词
- 城市
- 平台
- 薪资范围
- 方向池规模

## 3. 执行抓取并生成摘要

```bash
cd user_skills/job-radar
python3 scripts/job_radar.py search --profile assets/default_profile.yaml
```

脚本会输出 3 个文件路径：

- `job_radar_*.json`
- `job_radar_*.md`
- `job_radar_*.csv`

默认输出目录为当前工作目录下的 `job-radar-output/<timestamp>/`。

## 常见覆盖参数

### 只抓海外站点，不跑 BOSS

```bash
python3 scripts/job_radar.py search \
  --profile assets/default_profile.yaml \
  --sites linkedin,indeed,google
```

### 只抓 BOSS，北京岗位

```bash
python3 scripts/job_radar.py search \
  --profile assets/default_profile.yaml \
  --sites boss \
  --cities "北京"
```

### 临时改关键词和城市

```bash
python3 scripts/job_radar.py search \
  --profile assets/default_profile.yaml \
  --keywords "海外运营,Global Campaign,Creator Growth" \
  --cities "上海,杭州,remote"
```

### 把 Tier 2 / Tier 3 方向也拉进来

```bash
python3 scripts/job_radar.py search \
  --profile assets/default_profile.yaml \
  --keywords "海外运营,主播运营,社媒运营,内容运营,策略运营,GTM运营"
```

### 临时改薪资范围

```bash
python3 scripts/job_radar.py search \
  --profile assets/default_profile.yaml \
  --min-salary-k 20 \
  --max-salary-k 45
```

### 只看近 3 天岗位

```bash
python3 scripts/job_radar.py search \
  --profile assets/default_profile.yaml \
  --hours-old 72
```

### 指定某份简历运行

```bash
python3 scripts/job_radar.py search \
  --profile assets/default_profile.yaml \
  --resume-path "/path/to/your_resume.pdf"
```

### 首次自动拉取 BOSS 上游仓库

```bash
python3 scripts/job_radar.py search \
  --profile assets/default_profile.yaml \
  --sites boss \
  --bootstrap-boss
```

## 参数速查

| 参数 | 说明 |
| --- | --- |
| `--profile` | YAML 配置路径 |
| `--resume-path` | 显式指定本次使用的简历 |
| `--keywords` | 覆盖搜索词，逗号分隔 |
| `--score-keywords` | 覆盖打分关键词 |
| `--cities` | 覆盖城市，逗号分隔 |
| `--sites` | 覆盖平台 |
| `--min-salary-k` | 月薪下限 |
| `--max-salary-k` | 月薪上限 |
| `--hours-old` | 最近 N 小时窗口 |
| `--results-per-search` | JobSpy 每组搜索结果数 |
| `--boss-pages` | BOSS 每个关键词+城市抓取页数 |
| `--top-n` | Markdown 中展示前 N 个岗位 |
| `--remote-only` | 仅保留远程岗位 |
| `--output-dir` | 自定义输出目录 |
| `--boss-repo-path` | 自定义本地 BOSS 仓库路径 |
| `--bootstrap-boss` | 缺少 BOSS 仓库时自动 clone |

## BOSS 运行注意事项

BOSS 直聘部分依赖上游 `boss-zhipin-scraper`，通常需要本地已登录 Chrome 的 CDP 登录态。执行前建议确认：

- 本地 Chrome 已登录 BOSS
- Chrome 已打开远程调试端口（常见是 `9222`）
- 已执行 `python3 scripts/ensure_deps.py --with-boss`

如果环境没准备好，优先先跑 `linkedin/indeed/google`，并在结果里说明 BOSS 被跳过。

## 输出解读

`Markdown` 报告里默认包含：

- 摘要：搜索词、城市、平台、岗位数量、运行提示
- 推荐岗位表：投递优先级、方向分层、岗位、公司、前置投递链接、地点、薪资等
- 岗位详情：匹配说明、话术、cover letter 提示、JD 摘要

如果只需要把结果发给用户，优先返回 Markdown 文件；如果后续还要做二次处理，再同时使用 CSV / JSON。

## 定时任务边界

只有当用户明确要求“每天”“定时”“每周”时，才为这个 skill 配 schedule。默认先做一次抓取，不主动创建定时任务。
