---
name: job-radar
description: 求职抓岗与岗位日报技能：聚合 JobSpy 的 LinkedIn/Indeed/Google 岗位抓取，并可接入 boss-zhipin-scraper 抓取 BOSS 直聘；支持按关键词池、城市、remote、薪资范围筛选，输出结构化 JSON/CSV/Markdown 岗位摘要。适用于“帮我抓岗位”“按我的简历方向筛岗位”“做每日岗位汇总”“只做抓取+筛选+汇总、不自动投递”这类求职搜索任务。
author: yangyang.ajuj
---

# Job Radar

用于把“抓岗位 → 按画像筛选 → 输出可投递清单”做成稳定流程。

这个 skill **只做抓取、筛选和汇总**，不做自动投递。默认目标是尽快产出一份可以人工确认后再投递的岗位清单。

## 适用场景

以下情况优先使用本 skill：

- 用户要抓 LinkedIn、Indeed、Google Jobs 或 BOSS 直聘岗位；
- 用户给了简历方向、关键词池、城市、薪资范围，要求按条件筛岗位；
- 用户要做“今日新增岗位”“每日求职汇总”“岗位雷达”；
- 用户明确说**不要自动投递**，只要结果汇总。

如果用户是要管理投递进度、面试状态或 offer 流程，改用 `/offer`；如果用户是要包装简历内容，改用 `/asu` 或 `/resume`。

## 默认资源

- 默认画像配置：[`assets/default_profile.yaml`](assets/default_profile.yaml)
- 配置字段说明：[`references/profile-schema.md`](references/profile-schema.md)
- 常用命令配方：[`references/usage-recipes.md`](references/usage-recipes.md)

## 执行原则

1. 先确认用户要的只是**抓取+筛选+汇总**，不要擅自扩展到自动投递。
2. 首次运行前，先安装依赖。依赖脚本见 [scripts/ensure_deps.py](scripts/ensure_deps.py)：

   ```bash
   cd user_skills/job-radar && python3 scripts/ensure_deps.py
   cd user_skills/job-radar && python3 scripts/ensure_deps.py --with-boss
   ```

3. 先跑一次 `plan` 预览搜索矩阵，再决定是否真正抓取。
4. 输出优先使用 Markdown 摘要；如果后续还要二次分析，再同时保留 JSON / CSV。
5. 抓取前优先读取最新简历：默认会在 workspace 根目录、当前目录和 `assets/` 下寻找最新上传的 HTML / PDF / DOCX / MD / TXT 简历，并把提取出的亮点和关键词用于匹配理由、打招呼语和排序；如果用户明确指定简历文件，再通过 `--resume-path` 传入。
6. 如果用户只是临时改关键词、城市或薪资，优先使用命令行参数覆盖；只有用户明确要修改长期默认画像时，才编辑 `assets/default_profile.yaml`。

## 推荐工作流

### A. 预览搜索计划

```bash
cd user_skills/job-radar && python3 scripts/job_radar.py plan --profile assets/default_profile.yaml
```

### B. 执行抓取

```bash
cd user_skills/job-radar && python3 scripts/job_radar.py search --profile assets/default_profile.yaml
```

### C. 临时覆盖条件

```bash
cd user_skills/job-radar && python3 scripts/job_radar.py search \
  --profile assets/default_profile.yaml \
  --keywords "海外运营,Global Campaign,Creator Growth" \
  --cities "上海,杭州,remote" \
  --min-salary-k 20 \
  --max-salary-k 45 \
  --sites linkedin,indeed,google
```

## 平台策略

### JobSpy 平台

`linkedin`、`indeed`、`google`、`zip_recruiter`、`glassdoor` 由 `jobspy` 直接抓取，适合作为默认主路径。没有特殊要求时，优先先跑这些平台。

### BOSS 平台

`boss` 通过上游 `boss-zhipin-scraper` 接入。它通常依赖本地已登录 Chrome 的 CDP 登录态。

处理原则：

- 如果当前环境还没准备好 BOSS 登录态，不要卡住整个任务；先跑其他平台，并在结果里说明 BOSS 被跳过。
- 如果用户明确要求抓 BOSS，再补装 BOSS 依赖，并在命令里加 `--bootstrap-boss` 自动拉取上游仓库。
- 不复制上游 skill 逻辑，也不自动投递。

## 输出要求

抓取完成后，脚本会输出 3 个文件：

- `job_radar_*.md`：适合直接发给用户，默认包含投递优先级、方向分层、岗位/公司、前置的投递链接、一键投递备注、中英文打招呼语、cover letter 提示和 JD 摘要。报告中会明确指出本次使用了哪份简历。
- `job_radar_*.json`：适合做二次分析或后处理
- `job_radar_*.csv`：适合表格查看

向用户汇报时，优先给 Markdown 文件链接，并简要说明：

- 本次搜索词
- 城市与平台
- 筛选后的岗位数
- 是否有平台被跳过或失败

## 定时任务边界

只有当用户明确说“每天”“定时”“每周”时，才基于这个 skill 创建 schedule。默认只做一次抓取，不主动创建定时任务。
