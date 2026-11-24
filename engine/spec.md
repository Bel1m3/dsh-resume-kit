# 简历数据规格（resume-spec v2）

生成器只吃这一份 JSON。**字段全部可缺省，缺省即不渲染该块** —— 不要用占位符填充，
没有的信息就不写（这比写「XXXX」可信得多）。缺什么用 `resume_intake` 问用户。

```jsonc
{
  "template": "dark-blue",              // 必填：dark-blue | wine-ribbon | single-ats；不填会要求先选版式
  "basics": {
    "name": "林知远",                    // 必填
    "englishName": "SONG  WENBO",       // 可选，英文名/拼音（dark-blue 侧栏用）
    "photo": "assets/photos/me.jpg",    // dark-blue / wine-ribbon 必填；single-ats 可选（不放就删掉这段）
    "resumeTitle": "求职简历",            // 可选，single-ats 顶部大标，默认「求职简历」
    "skillsLine": "Revit、AutoCAD、广联达GTJ",  // 可选，single-ats 那行「擅长软件」，不给就从技能小节里取
    "headline": {                       // 可选，dark-blue 主栏顶部那行「求职意向」
      "label": "求职意向",
      "value": "中国铁路南昌局集团有限公司",
      "detail": "房建工程（站房建设、房屋维修改造）"
    },
    "fields": [                         // 侧栏「基础信息」逐行渲染
      { "label": "年龄", "value": "20 岁 · 2005.05" },
      { "label": "电话", "value": "138 0000 0000", "icon": "▪" }   // icon 可选
    ],
    "sideSections": [                   // 侧栏下方的小节，按数组顺序
      {
        "title": "技能证书",
        "style": "lines",               // lines（默认）| bars（进度条）| radar（雷达图）
        "lines": [
          { "label": "专业软件", "value": "Revit、AutoCAD、PyCharm" }
        ]
      },
      {
        "title": "技能特长",
        "style": "bars",
        "bars": [
          // percent 可省略：给 level 时按 精通 .92 / 擅长 .78 / 掌握 .74 / 良好 .72
          // 熟练 .70 / 熟悉 .66 / 一般 .50 / 了解 .38 / 入门 .25 折算；
          // 想精确控制就直接给 percent（0—1 或 0—100），优先级最高。
          { "label": "计算机：", "level": "精通", "percent": 0.92 }
        ]
      },
      {
        "title": "能力雷达",
        "style": "radar",
        "radar": [                      // 轴数与轴名都能改：增删维度、换名字都行
          { "label": "数理逻辑", "value": 0.78 }
        ]
      }
    ]
  },
  "layoutScale": 1.0,                   // 一般不用写：single-ats 超一页时插件会自动填 0.95 / 0.90
  "sections": [                          // 主栏小节，按数组顺序渲染
    {
      "type": "education",
      "title": "教育背景",
      "items": [
        {
          "period": "2023.09 — 2027.06",
          "school": "华东交通大学（土木建筑学院）",
          "major": "智能建造",
          "degree": "本科",
          "lines": [                     // 可选，教育条目下面的补充行
            { "label": "专业方向", "text": "土木类 · 智能建造；主修课程：建筑力学、土力学" }
          ]
        }
      ]
    },
    {
      "type": "experience",              // 实习 / 工作 / 项目 / 校园经历都用这个
      "title": "实习与工作经历",
      "items": [
        {
          "period": "2024.06 — 2025.09",
          "org": "共粒科技（南昌）有限责任公司",
          "role": "技术总监",
          "blocks": [                    // 【小标题】+ 正文
            { "label": "主要工作内容", "text": "面向工程建设的数字化建造系统研发与架构搭建" }
          ],
          "bullets": [                   // 缩进小条目，常用「（1）（2）」编号
            "（1）面向工程建设场景开展智能建造系统开发；"
          ],
          "footBlocks": [                // 可选，加在 bullets 之后的补充段
            { "label": "成果", "text": "参与省自然科学基金项目 1 项" }
          ]
        }
      ]
    },
    {
      "type": "bullets",                 // 一行一条的清单（项目与科研经历）
      "title": "项目与科研经历",
      "items": [
        { "text": "苏州东隧道 3# 盾构工作井围护结构分析项目", "role": "BIM 施工模拟" }
      ]
    },
    {
      "type": "awards",                  // 荣誉奖项：dark-blue 用点线引导，wine 用四列表格
      "title": "荣誉奖项",
      "items": [
        { "year": "2025", "name": " 全国大学生数学建模竞赛", "award": "省级二等奖",
          "level": "省部级", "team": "1/3", "highlight": true }
      ]
    },
    {
      "type": "text",                    // 自由段落（技能特长、自我评价）
      "title": "技能特长",
      "paragraphs": ["**计算机：**计算机二级证书，熟练操作建模软件。"]
    }
  ]
}
```

## 行内标记（只在这几种地方生效）

正文里的 `text` / `paragraphs` 支持两种标记，生成器会转成 Word 里的真实格式：

| 写法 | 效果 | 用在哪 |
|---|---|---|
| `**文字**` | 加粗（正文色） | 段首小标题、动作动词 |
| `{{文字}}` | 加粗 + 强调色（dark-blue 近黑，wine 酒红） | 量化成果、关键名词，全篇控制在 6 处以内 |

## 硬约束（会被校验）

1. `basics.name` 必填；`basics.photo` 在 `dark-blue` / `wine-ribbon` 必填（缺了插件会拦下来让你去要），在 `single-ats` 可选。
2. 所有数字、时间、单位必须来自用户，**模型不许自己编**。
3. 一页装不下时优先删 `bullets`，其次减少 `blocks`；不要缩字号。
4. `template` 必须是 `templates/index.json` 里存在的 id。
5. 照片会按版式画框的比例居中裁切（dark-blue 3.90×5.50cm，wine 3.39×3.72cm，single-ats 2.80×3.80cm），
   所以横图竖图都不会把版面撑变形。
