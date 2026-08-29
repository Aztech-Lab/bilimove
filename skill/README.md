# Skill: bilimove

Agent 可直接加载的 skill，让 LLM Agent 无需读代码/文档就能操作本项目。

## 结构

```
skill/
└── bilimove/
    └── SKILL.md        # 主 skill 定义（frontmatter: name + description）
```

## 使用

- **Agent 加载**：用 skill 加载机制读取 `skill/bilimove/SKILL.md`，按其中命令操作。
- **人类/Agent 手册**：项目根目录 `AGENT.md` 是完整手册，SKILL.md 是精简操作卡。
- **安装到 agent 环境**：把 `skill/bilimove/` 复制到你的 agent 的 skills 目录，或直接引用本仓库。

## 内容

SKILL.md 覆盖：环境准备、B 站登录、核心命令表、关键规则（转载 source、简介换行、封面 png、去重）、故障排查、扩展指南。
