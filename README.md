# openclaw-secretary

一个为 OpenClaw 设计的私人 AI 秘书技能包，围绕日历、目标、提醒、复盘和工作记忆构建。

它的目标不是“陪聊”，而是把大模型约束成一个真正可执行的秘书:
- 涉及日程、任务、目标时，必须先调用工具查数据库，不能靠上下文记忆回答
- 需要提醒时，必须注册定时器，不能只口头承诺
- 涉及个人数据的读写，只能在私聊里进行

## 项目在做什么

这个项目把“AI 秘书”拆成了三层:

1. Prompt 约束层
   通过 `SKILL.md`、`SECRETARY.md`、`PLANNING.md` 规定秘书模式下的行为边界、工具调用顺序和确认规则。
2. 工具执行层
   通过 `tools/*.py` 提供一组可被 OpenClaw 调用的 Python CLI 工具，负责读写日历、目标、提醒、画像、工作记忆等数据。
3. 数据持久层
   通过 SQLite 保存长期状态，让秘书具备真正的“可追踪记忆”，而不是完全依赖模型上下文。

一句话概括:

> OpenClaw 负责接消息和调度，大模型负责理解意图，Python 工具负责执行，SQLite 负责记住。

## 核心能力

### 1. 日历与特殊日期管理
- 查询今天、某个时间范围内的事项
- 新增、更新、删除日历事项
- 录入生日、纪念日等特殊日期
- 导入 `.ics` 文件
- 拉取节假日并扩展日历窗口

对应工具:
- `tools/calendar_tool.py`

### 2. 目标与进度管理
- 创建周/月/季度/长期目标
- 模糊搜索已有目标
- 记录每日进展日志
- 查看目标详情、修订历史、关联事项
- 重新计算进度
- 给出目标拆解建议

对应工具:
- `tools/goal_tool.py`

### 3. 提醒与定时任务
- 一次性提醒
- 周期性提醒
- 重型提醒: 到点唤醒 AI，结合上下文主动发起对话
- 轻型提醒: 到点直接发送固定消息
- 提醒投递目标控制，避免把私密提醒发错窗口

对应工具:
- `tools/timer_tool.py`

### 4. 用户画像与工作记忆
- 验证当前发消息的人是否是 owner
- 阻止群聊读取或写入私人秘书数据
- 保存用户画像
- 保存“以后都按这个习惯来”的行为规则

对应工具:
- `tools/profile_tool.py`
- `tools/working_memory_tool.py`

### 5. 复盘与长期追踪
- 保存每日总结
- 汇总每周总结
- 基于最近的复盘结果辅助后续规划
- 记录重要事件与随手备忘

对应工具:
- `tools/reflection_tool.py`
- `tools/memo_tool.py`
- `tools/resource_tool.py`

### 6. 本地可视化面板
- 浏览今日概览
- 浏览近期日历
- 查看活跃目标
- 查看周总结历史

对应工具:
- `tools/dashboard.py`

## 典型工作流

用户发来消息后，整体链路大致如下:

1. OpenClaw 命中 `secretary` skill
2. 模型读取 `SKILL.md` / `SECRETARY.md`
3. 先调用 `profile_tool.py check_access` 做私聊保护和身份校验
4. 根据用户意图调用具体工具:
   - 查日程: `calendar_tool.py`
   - 管目标: `goal_tool.py`
   - 设提醒: `timer_tool.py`
   - 记偏好: `working_memory_tool.py`
   - 做复盘: `reflection_tool.py`
5. 工具把结果写入或读取 `~/.openclaw/secretary/secretary.db`
6. 大模型基于工具返回结果组织成秘书式回复

核心原则:
- 不从聊天记忆直接回答日程问题
- 不在群聊里碰私人数据
- 不“口头答应”提醒，必须真正注册

## 数据存储

默认数据目录:

```bash
~/.openclaw/secretary/
```

主要文件:
- `secretary.db`: 主数据库
- `config.json`: 运行时配置
- `schema_version.txt`: schema 版本记录

数据库主要表:
- `calendar_events`
- `goals`
- `goal_logs`
- `goal_revisions`
- `timers`
- `user_profile`
- `working_memory`
- `daily_reflections`
- `weekly_reflections`
- `memos`
- `resources`
- `event_queue`

Schema 定义见:
- `db/schema.sql`

## 安装方式

### 方式一: 本地开发安装

适合你当前这个仓库本地直接开发、调试。

```bash
python3 local_install.py
```

它会做这些事:
- 安装 Python 依赖
- 初始化或迁移数据库
- 生成 `~/.openclaw/secretary/config.json`
- 将 skill 安装到 `~/.openclaw/workspace/skills/secretary`
- 生成最终给 OpenClaw 注入的 `SKILL.md`

### 方式二: 通过 OpenClaw 安装

仓库里的 `SKILL.md` frontmatter 已声明安装脚本:

```yaml
metadata:
  openclaw:
    install:
      - kind: exec
        command: "python3 {baseDir}/install.py"
```

即 OpenClaw 安装 skill 时会执行:

```bash
python3 install.py
```

## 依赖

运行时依赖主要包括:
- `python3`
- `flask`
- `flask-cors`
- `lunardate`
- `requests`
- `icalendar`

安装脚本会自动安装这些 Python 包。

## 使用方式

### 1. 启用 skill

安装完成后，OpenClaw 中的 `secretary` skill 会生效。

### 2. 打开本地 Dashboard

```bash
python3 tools/dashboard.py
```

默认会打开:

```text
http://localhost:5299
```

端口可在 `~/.openclaw/secretary/config.json` 中修改。

### 3. 直接调用工具调试

示例:

```bash
python3 tools/calendar_tool.py read_today '{}'
python3 tools/goal_tool.py get_active_summary '{}'
python3 tools/timer_tool.py list_timers '{"status":"active"}'
python3 tools/profile_tool.py get_config '{}'
```

## Prompt 文件说明

项目中的提示词文件分工如下:

- `SKILL.md`
  OpenClaw skill 入口，定义安装信息、启用条件和高层规则
- `SECRETARY.md`
  秘书模式的完整行为规范
- `PLANNING.md`
  进入规划模式后追加注入的规则
- `PERSONA.md`
  秘书人设、语气和工作风格
- `PROMPTS_GUIDE.md`
  提示词文件和配置项说明

其中:
- `PERSONA.md` 适合高频调整
- `SECRETARY.md` / `PLANNING.md` 更偏底层行为协议，不建议频繁改

修改这些文件后，重新运行:

```bash
python3 local_install.py
```

使生成后的 skill 文件更新。

## 目录结构

```text
openclaw-secretary/
├── README.md
├── SKILL.md
├── SECRETARY.md
├── PLANNING.md
├── PERSONA.md
├── PROMPTS_GUIDE.md
├── install.py
├── local_install.py
├── start_gateway.sh
├── dashboard/
│   └── index.html
├── assets/
│   └── lunar_calendar.ics
├── db/
│   ├── schema.sql
│   └── migrations/
└── tools/
    ├── _common.py
    ├── calendar_tool.py
    ├── dashboard.py
    ├── event_queue_tool.py
    ├── goal_tool.py
    ├── memo_tool.py
    ├── plan_tool.py
    ├── profile_tool.py
    ├── reflection_tool.py
    ├── resource_tool.py
    ├── timer_tool.py
    └── working_memory_tool.py
```

## 当前状态说明

这个仓库已经具备完整的秘书主链路:
- 日历
- 目标
- 提醒
- 用户画像
- 工作记忆
- 日复盘 / 周总结
- Dashboard

同时也保留了一些项目演进痕迹:
- 早期 `plan_tool` 方案后来迁移到了 `goal_tool`
- `db/migrations/` 里保留了从 `plans` 迁移到 `goals` 的脚本

如果你继续迭代这个项目，建议优先统一:
- 文档里主推的能力边界
- `plan_tool` 与 `goal_tool` 的角色
- schema 版本与迁移脚本的对应关系

## 适用场景

这个项目适合以下场景:
- 个人时间管理
- 私人助理式任务推进
- 周计划 / 月计划跟踪
- 每日复盘与每周复盘
- 需要“工具可信、数据可追踪”的 AI 助手

不适合:
- 完全开放式群聊助手
- 无状态的一次性问答助手
- 不希望引入数据库持久化的轻量脚本场景

## License

仓库当前未声明 License。
如果你准备公开发布，建议补充一个明确的开源许可证。
