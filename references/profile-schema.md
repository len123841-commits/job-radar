# 配置文件说明

`assets/default_profile.yaml` 是求职抓岗 skill 的默认配置。需要临时调整时，优先在命令行通过 `--keywords`、`--cities`、`--sites`、`--min-salary-k`、`--max-salary-k` 或 `--resume-path` 覆盖；只有当用户明确想改默认画像时，才直接修改 YAML。

## 配置结构

```yaml
version: 1
candidate:
  name: 候选人名称
  note: 对岗位方向的自然语言补充
  highlights:
    - 候选人的可复用亮点，用于生成打招呼语
  search_terms:
    - 用于实际检索的搜索词
  direction_pool:
    tier_1_strong:
      - 强匹配岗位方向
    tier_2_potential:
      - 可尝试岗位方向
    tier_3_extended:
      - 延展岗位方向
  score_keywords:
    - 用于打分与解释的关键词
search:
  cities:
    - 当前默认启用的城市
  city_pool:
    tier_1_major:
      - 当前最优先城市
    tier_2_east_china:
      - 华东备选城市
    tier_2_south_china:
      - 华南备选城市
    tier_2_central_china:
      - 华中备选城市
    tier_2_north_china:
      - 华北备选城市
    tier_2_west_china:
      - 西部备选城市
    tier_2_northeast_china:
      - 东北备选城市
    tier_3_others:
      - 其他地区城市
  remote_ok: true
  min_monthly_salary_k: 15
  max_monthly_salary_k: 60
  platforms:
    - linkedin
    - indeed
    - google
    - boss
  jobspy_results_per_search: 20
  boss_pages_per_keyword_city: 1
  hours_old: 168
output:
  top_n: 50
```

## 动态简历读取

脚本在每次抓取前会优先寻找最新上传的简历文件，默认搜索这些位置：

- workspace 根目录
- `user_skills/job-radar/assets/`
- 当前运行目录

支持的格式包括：HTML、PDF、DOCX、Markdown、TXT。

处理规则：

1. 如果命令显式传了 `--resume-path`，优先使用该文件。
2. 否则自动选择上述位置里最近修改的一份简历文件。
3. 从简历中抽取亮点与关键词，用于补强 `score_keywords`、生成匹配理由、中英文打招呼语、一键投递备注与投递排序。
4. 如果未找到可读简历，才回退到 `default_profile.yaml` 里的静态 `highlights`。

## 字段解释

### `candidate.highlights`

用于生成定制打招呼语的候选人亮点池。建议写成可直接复用的成果短句，例如：

- TikTok Gaming LIVE 海外运营
- UK/FR/DE/AU 多区域 Campaign 交付
- DE 活动增量 $130k→$320k，ROI 提升 12pct
- 站内信触达链路 0→1，累计触达近 50 万主播
- AI 违规初筛 Precision 95%、Recall 100%

### `candidate.search_terms`

真正拿去搜索招聘站点的词。适合放岗位名、方向词或常见中英文搜索词，例如：

- 海外运营
- Global Campaign
- Creator Growth
- TikTok LIVE 运营

### `candidate.direction_pool`

扩展岗位方向默认池。它主要用于**分层排序和保留方向备选项**，例如：

- Tier 1：最贴简历、最优先投递
- Tier 2：可尝试的相关方向
- Tier 3：延展方向

注意：如果你希望某个方向**真的参与抓取**，只放在 `direction_pool` 里还不够，最好同时把它加入 `search_terms`，或者运行时通过 `--keywords` 显式传入。举例：

- 只想搜强相关方向：`--keywords "海外运营,Global Campaign,Creator Growth"`
- 想把拓展方向也搜出来：`--keywords "海外运营,社媒运营,内容运营,策略运营,GTM运营"`

### `candidate.score_keywords`

用于给岗位打“相关度”的关键词池。可以比 `search_terms` 更宽，例如：

- TikTok
- LIVE
- creator
- campaign
- growth
- marketing
- AI

### `search.cities`

当前默认启用的抓取城市。支持直接写 `remote`，脚本会把它视为远程岗位偏好。

### `search.city_pool`

全国城市可选池。它本身不会直接扩大抓取范围，主要用于保留更完整的城市备选项；需要启用某个城市时，再把它加入 `search.cities`。

### `search.platforms`

可选值：

- `linkedin`
- `indeed`
- `google`
- `zip_recruiter`
- `glassdoor`
- `boss`

其中 `boss` 需要额外准备 `boss-zhipin-scraper` 运行环境和本地登录态。

### 薪资字段

`min_monthly_salary_k` / `max_monthly_salary_k` 都按“月薪 K”理解。

- BOSS 的 `20-30K` 会直接按月薪处理。
- JobSpy 的年薪数据会换算成月薪 K。
- 无法换算的时薪、日薪或未标薪岗位默认保留，不会因为未知薪资被直接过滤掉。

## 调整建议

如果用户临时改筛选条件，优先：

1. 保持 `assets/default_profile.yaml` 不动；
2. 在命令里传覆盖参数；
3. 只有用户明确要更新长期默认画像，才改 YAML 并保留合理注释。
