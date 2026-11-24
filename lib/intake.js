/**
 * 缺失项体检：给定版式 + 已有数据，算出「还差什么」以及该问用户哪句话。
 *
 * 设计原则：
 *   · 只报真正影响这一版版面的缺口，不做泛泛的「信息越全越好」；
 *   · 每条都给一句可以直接发给用户的话（question），Agent 不需要再改写；
 *   · 不给默认值、不编内容，缺就是缺。
 */

/** 通用：姓名是唯一硬性必填。 */
const BASE_RULES = [
  {
    key: 'name',
    test: (spec) => Boolean(spec.basics?.name),
    question: '简历上写谁的名字？中文姓名就行。',
    example: '张三',
    required: true,
  },
  {
    key: 'contact',
    test: (spec) => {
      const fields = spec.basics?.fields || []
      const has = (kw) => fields.some((f) => String(f.label || '').includes(kw) && String(f.value || '').trim())
      return has('电话') || has('手机') || has('邮箱') || has('mail')
    },
    question: '留哪个联系方式给 HR？手机号和邮箱至少给一个。',
    example: '13800000000 / zhang@example.com',
    required: true,
  },

  {
    key: 'education',
    test: (spec) => (spec.sections || []).some((s) => s.type === 'education' && (s.items || []).length),
    question: '教育背景怎么填？需要学校、专业、学历、起止时间。',
    example: '2022.09—2026.06 某某大学 智能建造 本科',
    required: true,
  },
  {
    key: 'experience',
    test: (spec) => (spec.sections || []).some(
      (s) => s.type === 'experience' && (s.items || []).some((i) => (i.blocks || []).length || (i.bullets || []).length || (i.lines || []).length),
    ),
    question: '至少写一段实习/项目/校园经历：做了什么、结果怎样。没有数量就先写事实，别编数字。',
    example: '2025.03—2025.06 某设计院 实习生：参与 2 个住宅项目方案，独立完成 3 版总图',
    required: true,
  },
]

/** 版式专属：这些空着不算错，但版面会明显塌一块。 */
const TEMPLATE_RULES = {
  'dark-blue': [
    {
      key: 'photo',
      test: (spec) => Boolean(spec.basics?.photo),
      question: '这一版左栏顶部有照片位，必须要一张证件照：把图片路径发我就行（JPG/PNG）。',
      example: 'D:/photos/me.jpg',
      required: true,
    },
    {
      key: 'headline',
      test: (spec) => Boolean(spec.basics?.headline?.value),
      question: '这一版主栏顶上有一行「求职意向」，要投哪家单位、什么方向？',
      example: '中国铁路南昌局集团有限公司 · 房建工程',
      required: false,
    },

    {
      key: 'sideSections',
      test: (spec) => (spec.basics?.sideSections || []).some((b) => (b.lines || []).length),
      question: '左栏还能放「技能证书」和「自我评价」，有什么软件、证书、语言能力要写？',
      example: '专业软件：Revit、AutoCAD；证书：CET-4、1+X 智能建造',
      required: false,
    },
    {
      key: 'awards',
      test: (spec) => (spec.sections || []).some((s) => s.type === 'awards' && (s.items || []).length),
      question: '有竞赛/荣誉吗？这一版有「荣誉奖项」段，没有的话我就把这段去掉。',
      example: '2025 全国大学生数学建模竞赛 省级二等奖',
      required: false,
    },
  ],
  'wine-ribbon': [
    {
      key: 'photo',
      test: (spec) => Boolean(spec.basics?.photo),
      question: '这一版是围绕照片排的，必须要一张证件照：把图片路径发我就行（JPG/PNG）。',
      example: 'D:/photos/me.jpg',
      required: true,
    },
    {
      key: 'bars',
      test: (spec) => (spec.basics?.sideSections || []).some((b) => (b.bars || []).length >= 3),
      question: '左栏技能进度条：我从你上传的简历里把你会的软件/技能提取成条目，没写熟练度的先按「熟练」占位——你可以直接说「Python 改精通」「删掉摄影」，或者说「不要进度条」，我就整块去掉。',
      example: '计算机：精通；英语：熟练；数据分析：擅长 60%',
      required: false,
    },
    {
      key: 'radar',
      test: (spec) => (spec.basics?.sideSections || []).some((b) => (b.radar || b.axes || []).length >= 5),
      question: '左栏底部是能力雷达图，默认 8 维（数理逻辑/言语理解/资料分析/统筹领导/艺术绘画/人文社科/思政素养/专业素养）。你按 0—100 给自己打分我就画；维度可以增删改名，说「不要雷达」这块就整块去掉。',
      example: '数理逻辑 78、言语理解 62、资料分析 72 …',
      required: false,
    },
    {
      key: 'awards',
      test: (spec) => (spec.sections || []).some((s) => s.type === 'awards' && (s.items || []).length),
      question: '有竞赛获奖吗？这一版有「竞赛荣誉」段，需要赛事名 + 级别 + 奖项 + 团队排名。',
      example: '2025 蓝桥杯视觉艺术设计赛 省部级 二等奖 团队 2/2',
      required: false,
    },
  ],
  'single-ats': [
    {
      key: 'photo',
      test: (spec) => Boolean(spec.basics?.photo),
      question: '这一版照片可选：要放就把图片路径发我；不想放（有些网申系统不看照片）就说不放，我按无照片排版。',
      example: 'D:/photos/me.jpg',
      required: false,
    },
    {
      key: 'headline',
      test: (spec) => Boolean(spec.basics?.headline?.value),
      question: '网申系统会先读这一行判断岗位匹配度，求职意向写清楚：投哪个单位、什么岗位。',
      example: '中国铁路南昌局集团有限公司 · 房建工程',
      required: false,
    },
    {
      key: 'keywords',
      test: (spec) => {
        const text = JSON.stringify(spec)
        return /BIM|Revit|AutoCAD|Python|Office|CET|证书|软件/.test(text)
      },
      question: '机筛靠关键词打分：JD 里出现的软件、证书、技能名称原样写进「技能证书」，别只写「熟练使用办公软件」。',
      example: 'Revit、AutoCAD、广联达GTJ、CET-6、二级建造师',
      required: false,
    },
  ],
}

/** 数据质量提醒（不阻断生成）。 */
function qualityWarnings(spec) {
  const out = []
  const sections = spec.sections || []
  const exp = sections.filter((s) => s.type === 'experience')
  const count = exp.reduce((n, s) => n + (s.items || []).length, 0)
  if (count > 4) out.push(`经历共 ${count} 条，一页大概率放不下，建议合并到 3 段以内`)

  const text = JSON.stringify(spec)
  const placeholders = text.match(/x{4,}|X{4,}|待补充|（待填）/gi)
  if (placeholders) out.push(`检测到疑似占位符 ${placeholders.length} 处，交付前要换成真实内容`)

  const missingBlocks = exp.some((s) => (s.items || []).some(
    (i) => !(i.blocks || []).length && !(i.bullets || []).length && !(i.lines || []).length,
  ))
  if (missingBlocks) out.push('有经历条目只有单位/角色，没写做了什么 —— 面试官会直接跳过这段')

  // 粗略估一页装不装得下：中文一页约 1800—2200 字（含标点）
  let chars = 0
  const walk = (node) => {
    if (typeof node === 'string') chars += node.replace(/\s/g, '').length
    else if (Array.isArray(node)) node.forEach(walk)
    else if (node && typeof node === 'object') Object.values(node).forEach(walk)
  }
  walk(sections)
  if (chars > 2300) out.push(`正文约 ${chars} 字，单栏一页大概率放不下（建议压到 1800 字以内，或删掉最弱的一段）`)

  return out
}

export function analyze(spec = {}, template = 'dark-blue', templates = []) {
  const rules = [...BASE_RULES, ...(TEMPLATE_RULES[template] || [])]
  const missing = []
  for (const rule of rules) {
    let ok = false
    try {
      ok = rule.test(spec)
    } catch {
      ok = false
    }
    if (!ok) {
      missing.push({
        key: rule.key,
        question: rule.question,
        example: rule.example,
        required: rule.required,
      })
    }
  }
  const meta = templates.find((t) => t.id === template) || {}
  const blocking = missing.filter((m) => m.required)
  return {
    template,
    templateName: meta.name || template,
    ready: blocking.length === 0,
    missing,
    blocking: blocking.length,
    warnings: qualityWarnings(spec),
    nextStep: blocking.length
      ? '先把 required 的几条问清楚，再组织数据生成；不要替用户编内容。'
      : missing.length
        ? '必填项齐了，可先出一版；remaining 的条目可以生成后追问，让用户自己决定补不补。'
        : '信息齐了，可以直接生成。',
  }
}
