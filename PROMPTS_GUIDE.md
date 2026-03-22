# Prompts Guide — 提示词文件说明

本文件说明 Secretary Skill 所有可配置的提示词文件，以及如何自定义它们。

修改任意文件后，重新运行 `python3 local_install.py` 使修改生效。

---

## 文件一览

| 文件 | 路径 | 作用 | 修改频率 |
|------|------|------|----------|
| `PERSONA.md` | `/Users/hih/openclaw-secretary/PERSONA.md` | 秘书人设（名字、性格、沟通风格） | 按需 |
| `SECRETARY.md` | `/Users/hih/openclaw-secretary/SECRETARY.md` | 秘书模式完整行为规范（工具调用、行为约束、onboarding 等） | 很少 |
| `PLANNING.md` | `/Users/hih/openclaw-secretary/PLANNING.md` | 规划模式提示词（仅在进入规划模式时加载） | 很少 |
| `config.json` | `~/.openclaw/secretary/config.json` | 运行时配置（时区、激活语、dashboard 端口等） | 按需 |

生成后的合并文件（不要直接修改）：

| 文件 | 路径 | 说明 |
|------|------|------|
| `SKILL.md` | `~/.openclaw/workspace/skills/secretary/SKILL.md` | 由 `local_install.py` 自动生成，合并了 PERSONA + SECRETARY |

---

## PERSONA.md — 秘书人设

**路径**：`/Users/hih/openclaw-secretary/PERSONA.md`

可以修改的内容：
- **代号**：秘书的名字/称呼（默认「秘书小C」）
- **性格**：形容词描述，影响 AI 的回复风格
- **工作风格**：如何处理任务、汇报结果的偏好
- **对话语气**：正式/随意，严谨/活泼

修改示例 — 让秘书更活泼：
```markdown
## 性格
专业、活泼、偶尔幽默。处理严肃事务时沉稳，日常沟通轻松自然。
```

---

## config.json — 运行时配置

**路径**：`~/.openclaw/secretary/config.json`

| 字段 | 默认值 | 说明 |
|------|--------|------|
| `activation_message` | `"您好，秘书小C为您服务。"` | 每次首次进入秘书模式时说的第一句话 |
| `timezone` | `"Asia/Shanghai"` | 时区（影响日历和定时任务） |
| `dashboard_port` | `5299` | Dashboard 服务端口 |
| `holiday_region` | `"CN"` | 节假日区域（CN = 中国大陆） |
| `owner_verify` | `true` | 是否开启发送者身份验证（单用户私聊可设为 false） |
| `onboarding_done` | `false` | 是否完成初始化（首次对话后自动设为 true） |

修改 `activation_message` 示例：
```json
{
  "activation_message": "在的，老板。"
}
```
修改后重新运行 `python3 local_install.py` 使激活语更新到 SKILL.md。

---

## SECRETARY.md — 核心行为规范

**路径**：`/Users/hih/openclaw-secretary/SECRETARY.md`

包含以下章节，可按需调整：

| 章节 | 说明 | 常见自定义 |
|------|------|----------|
| 一、身份验证 | owner_id 验证逻辑 | 调整 `owner_verify` 行为 |
| 二、初始化步骤 | 进入秘书模式时自动执行的4个工具调用 | 可增减初始化内容 |
| 五、行为约束 | 哪些操作需确认，哪些直接执行 | 根据个人习惯调整确认粒度 |
| 六、行程录入规则 | 如何处理冲突、提示 | 可调整冲突严重程度的阈值 |
| 八、Onboarding | 首次使用的引导流程 | 可调整采集的信息项 |

**建议**：非技术用户不要修改此文件，通过 PERSONA.md 和 config.json 满足大多数定制需求。

---

## PLANNING.md — 规划模式

**路径**：`/Users/hih/openclaw-secretary/PLANNING.md`

仅在用户主动发起规划讨论时加载（由 AI 执行 `read PLANNING.md`）。

包含：
- 规划原则（弹性优先、粒度控制）
- 5步规划流程
- 任务字段规范

---

## 工作流程

```
用户修改文件 → python3 local_install.py → 重启 openclaw gateway
```

验证：
```bash
cat ~/.openclaw/workspace/skills/secretary/SKILL.md | head -50
```
