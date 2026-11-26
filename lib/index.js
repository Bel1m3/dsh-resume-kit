/**
 * dsh-resume-kit — 宿主侧入口：三个工具。
 *
 *   resume_template_list  列出内置版式及其适用/不适用场景（第一步，先让用户挑）
 *   resume_intake         按选定版式体检数据，返回缺什么、该问用户哪句话
 *   resume_generate       把一份结构化简历数据渲染成可编辑的 .docx（可选同时导出 PDF）
 *
 * 设计约束：
 *   · 不联网、不抓取任何平台内容；版式是仓库里的静态资产。
 *   · 渲染交给 python-docx（DSH 桌面端自带运行时的 python），避免在 Node 里手搓 OOXML。
 *   · PDF 走 DSH 自带的 LibreOffice Kit；找不到就只出 docx，并在 warnings 里说明。
 */
import { spawn } from 'node:child_process'
import { existsSync, mkdirSync, readFileSync, rmSync, writeFileSync } from 'node:fs'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { homedir } from 'node:os'
import { analyze } from './intake.js'

export const name = 'dsh-resume'
export const inject = ['tools']

const PKG_ROOT = resolve(dirname(fileURLToPath(import.meta.url)), '..')
const ENGINE = join(PKG_ROOT, 'engine', 'build_resume.py')
const TEMPLATE_INDEX = join(PKG_ROOT, 'templates', 'index.json')

// ---------------------------------------------------------------- 运行时探测

const execDir = () => dirname(process.execPath)

/** 依次尝试：配置 → 环境变量 → DSH 桌面端自带运行时 → PATH 上的 python。 */
function findPython(config = {}) {
  const candidates = [
    config.python,
    process.env.DSH_RESUME_PYTHON,
    join(execDir(), 'resources', 'office-runtime', 'primary-runtime', 'dependencies', 'python', 'python.exe'),
    join(execDir(), 'resources', 'office-runtime', 'primary-runtime', 'dependencies', 'python', 'bin', 'python3'),
  ].filter(Boolean)
  for (const candidate of candidates) {
    if (existsSync(candidate)) return { command: candidate, bare: false }
  }
  return { command: process.platform === 'win32' ? 'python' : 'python3', bare: true }
}

/** LibreOffice Kit：用 DSH 自己的可执行文件以 node 模式跑 office-cli。 */
function findKit(config = {}) {
  const cli = config.officeCli || join(execDir(), 'resources', 'office-cli.mjs')
  if (!existsSync(cli)) return null
  return { node: config.officeNode || process.execPath, cli }
}

function run(command, args, { timeoutMs = 120_000, env = {} } = {}) {
  return new Promise((resolvePromise) => {
    const child = spawn(command, args, {
      env: { ...process.env, ...env },
      windowsHide: true,
    })
    let stdout = ''
    let stderr = ''
    const timer = setTimeout(() => child.kill(), timeoutMs)
    child.stdout.on('data', (chunk) => {
      stdout += chunk.toString()
    })
    child.stderr.on('data', (chunk) => {
      stderr += chunk.toString()
    })
    child.on('error', (error) => {
      clearTimeout(timer)
      resolvePromise({ code: -1, stdout, stderr: stderr + (error?.message || String(error)) })
    })
    child.on('close', (code) => {
      clearTimeout(timer)
      resolvePromise({ code, stdout, stderr })
    })
  })
}

// ---------------------------------------------------------------- 校验

const PLACEHOLDER = /x{4,}|X{4,}|（待填）|待补充/i

/** 扫出明显的占位符：简历里出现 "XXXX" 是最常见的偷懒，必须提醒。 */
function scanPlaceholders(node, path = '', hits = []) {
  if (node == null) return hits
  if (typeof node === 'string') {
    if (PLACEHOLDER.test(node)) hits.push(`${path || 'root'}: ${node.slice(0, 40)}`)
    return hits
  }
  if (Array.isArray(node)) {
    node.forEach((item, index) => scanPlaceholders(item, `${path}[${index}]`, hits))
    return hits
  }
  if (typeof node === 'object') {
    for (const [key, value] of Object.entries(node)) scanPlaceholders(value, path ? `${path}.${key}` : key, hits)
  }
  return hits
}

function loadTemplates() {
  try {
    const list = JSON.parse(readFileSync(TEMPLATE_INDEX, 'utf8'))
    return Array.isArray(list) ? list : []
  } catch {
    return []
  }
}

/** 照片必须能找到：所有版式都留了照片位，找不到就直接拦下来，别生成一张空照片的简历。 */
function resolvePhoto(raw, baseDir) {
  if (!raw) return null
  const candidates = []
  if (/^[A-Za-z]:[\\/]/.test(raw) || raw.startsWith('/')) {
    candidates.push(raw)
  } else {
    if (baseDir) candidates.push(join(baseDir, raw))
    candidates.push(join(PKG_ROOT, raw))
    candidates.push(resolve(raw))
  }
  for (const candidate of candidates) {
    if (existsSync(candidate)) return candidate
  }
  return null
}

/** 数一下 PDF 有几页：数 /Type /Page（排除 /Pages）就够了，不用引三方库。 */
function countPdfPages(path) {
  try {
    const text = readFileSync(path).toString('latin1')
    const hits = text.match(/\/Type\s*\/Page[^s]/g)
    return hits ? hits.length : null
  } catch {
    return null
  }
}

function resolveOutDir(input) {
  if (input && typeof input === 'string') return resolve(input)
  const fallback = join(process.env.DSH_HOME || join(homedir(), '.dsh'), 'resume-out')
  return fallback
}

// ---------------------------------------------------------------- 工具实现

async function generate(args, exec, config) {
  if (!args || typeof args !== 'object') throw new Error('缺少参数对象')
  if (typeof exec?.signal?.throwIfAborted === 'function') exec.signal.throwIfAborted()

  const templates = loadTemplates()
  const requested = typeof args.template === 'string' ? args.template.trim() : ''
  if (!requested) {
    // 不替用户默认选版式：三套的适用岗位差很多，必须先把选择摆到用户面前
    const list = templates.map((t) => `  · ${t.id}（${t.name}）—— ${t.bestFor?.[0] || ''}`).join('\n')
    throw new Error(`还没选版式。请先把这三套摆给用户挑，再用它的 id 重新调用：\n${list}\n不选版式不会替你默认用第一套。`)
  }
  const templateId = requested
  if (!templates.some((item) => item.id === templateId)) {
    throw new Error(`没有这个版式：${templateId}（可选：${templates.map((t) => t.id).join('、')}）`)
  }

  // 数据来源：对象 / JSON 字符串 / 文件路径，三选一
  let spec = args.data
  let baseDir = null
  if (typeof spec === 'string') {
    const text = spec.trim()
    if (text.startsWith('{')) spec = JSON.parse(text)
    else if (existsSync(text)) {
      baseDir = dirname(resolve(text))
      spec = JSON.parse(readFileSync(text, 'utf8'))
    } else throw new Error('data 既不是 JSON 也不是已存在的文件路径')
  }
  if (!spec || typeof spec !== 'object') throw new Error('缺少简历数据（data）')
  // 工具参数里的对象是只读的，复制一份再改，否则 spec.template = ... 会抛 read only
  spec = JSON.parse(JSON.stringify(spec))
  spec.template = templateId

  // 相对照片路径按「数据文件所在目录」解析，再交给引擎兜底
  if (baseDir && spec.basics?.photo && !/^[A-Za-z]:[\\/]/.test(spec.basics.photo) && !spec.basics.photo.startsWith('/')) {
    const candidate = resolve(baseDir, spec.basics.photo)
    if (existsSync(candidate)) spec.basics.photo = candidate
  }

  const basics = spec.basics || {}
  if (!basics.name) throw new Error('basics.name 必填：至少要给一个名字')

  // 深灰蓝 / 酒红绶带必须带照片；单栏 ATS 允许用户选择不放照片
  const photoOptional = templateId === 'single-ats'
  const photoPath = resolvePhoto(basics.photo, baseDir)
  if (!photoPath) {
    if (basics.photo && !photoOptional) {
      throw new Error(`找不到这张照片：${basics.photo}。请确认路径，或让用户重新发一张（JPG/PNG）。`)
    }
    if (!photoOptional) {
      throw new Error('这套版式要求带照片：请先向用户要一张证件照（图片路径），再调用一次生成。')
    }
    delete basics.photo
  } else {
    basics.photo = photoPath
  }

  const warnings = []
  const placeholders = scanPlaceholders(spec).filter((hit) => !hit.startsWith('template'))
  if (placeholders.length) {
    warnings.push(`检测到疑似占位符 ${placeholders.length} 处，交付前应替换成真实内容：${placeholders.slice(0, 3).join('；')}`)
  }
  const report = analyze(spec, templateId, templates)
  for (const warning of report.warnings) {
    if (!warnings.includes(warning)) warnings.push(warning)
  }
  for (const item of report.missing) {
    warnings.push(`${item.required ? '必填缺失' : '建议补充'}：${item.key} —— ${item.question}`)
  }

  const outDir = resolveOutDir(args.outDir)
  mkdirSync(outDir, { recursive: true })

  const safeName = String(args.fileName || basics.name).replace(/[\\/:*?"<>|]/g, '').slice(0, 40) || 'resume'
  const docxPath = join(outDir, `${safeName}.docx`)
  const specPath = join(outDir, `.${safeName}.spec.json`)
  const pdfPath = docxPath.replace(/\.docx$/i, '.pdf')
  const python = findPython(config)
  const kit = findKit(config)

  const renderOnce = async () => {
    writeFileSync(specPath, JSON.stringify(spec, null, 2), 'utf8')
    const render = await run(python.command, [ENGINE, '--input', specPath, '--output', docxPath], {
      timeoutMs: 120_000,
    })
    if (render.code !== 0 || !existsSync(docxPath)) {
      const tail = (render.stderr || render.stdout || '').trim().split('\n').slice(-6).join('\n')
      throw new Error(`渲染失败（退出码 ${render.code}）${python.bare ? '，且没找到 DSH 自带的 Python' : ''}：\n${tail}`)
    }
    if (args.pdf === false) return { pdf: null, pages: null }
    if (!kit) return { pdf: null, pages: null, noKit: true }
    // LibreOffice 不会覆盖已存在的 PDF，先删掉旧文件，避免第二次生成时静默失败
    try {
      rmSync(pdfPath, { force: true })
    } catch {}
    const convert = await run(kit.node, [kit.cli, 'convert', '--input', docxPath, '--output', pdfPath], {
      timeoutMs: 120_000,
      env: { ELECTRON_RUN_AS_NODE: '1' },
    })
    if (convert.code !== 0 || !existsSync(pdfPath)) return { pdf: null, pages: null }
    return { pdf: pdfPath, pages: countPdfPages(pdfPath) }
  }

  // 单栏版「尽量一页」：排出来超过一页就按 0.95 / 0.90 再排一次
  const scales = templateId === 'single-ats' ? [1.0, 0.95, 0.9] : [1.0]
  let last = { pdf: null, pages: null }
  let usedScale = 1.0
  for (const scale of scales) {
    if (scale !== 1.0) spec.layoutScale = scale
    usedScale = scale
    last = await renderOnce()
    if (last.noKit) {
      warnings.push('没找到 LibreOffice Kit，只生成了 docx；PDF 可以在 DSH 里用 office 工具转换')
      break
    }
    if (args.pdf === false) break
    if (!last.pdf) {
      warnings.push('PDF 转换失败，docx 已生成')
      break
    }
    if (last.pages == null || last.pages <= 1) break
  }
  // 让落盘的 spec 与实际渲染一致，方便复现
  if (usedScale < 1) spec.layoutScale = usedScale
  else delete spec.layoutScale
  try {
    writeFileSync(specPath, JSON.stringify(spec, null, 2), 'utf8')
  } catch {}
  const pageCount = last.pages
  const pdfPathOut = last.pdf
  if (pdfPathOut && pageCount && pageCount > 1) {
    warnings.push(`单栏版压到最小字号仍是 ${pageCount} 页（已按 ${Math.round(usedScale * 100)}% 排），需要删掉一段经历或压到 1800 字以内`)
  } else if (pdfPathOut && usedScale < 1) {
    warnings.push(`为把单栏版压进一页，正文已自动缩到 ${Math.round(usedScale * 100)}%（如果再删一两行，可以恢复原字号）`)
  }

  const template = templates.find((item) => item.id === templateId)
  const result = {
    ok: true,
    template: templateId,
    templateName: template?.name,
    docx: docxPath,
    pdf: pdfPathOut,
    outDir,
    pages: pageCount,
    warnings,
    missing: report.missing,
    nextSteps: [
      '把 docx 打开通读一遍，确认每条数字都是用户真实提供的',
      '投递前建议用 ATS 工具或纯文本粘贴自检：双栏版式在部分筛选系统里会错序',
    ],
  }
  if (usedScale < 1) result.layoutScale = usedScale
  return result
}

// ---------------------------------------------------------------- 注册

export function apply(ctx, config = {}) {
  const register = (definition) => {
    try {
      ctx.tools.register(definition)
    } catch (error) {
      console.error(`[dsh-resume] 注册工具 ${definition.name} 失败：${error?.message || error}`)
    }
  }

  register({
    name: 'resume_template_list',
    description:
      '列出内置简历版式，以及每个版式适合/不适合的岗位与场景。**这是第一步**：用户一说要做简历，先调它，把三套摆给用户挑（别自己替用户选）；resume_intake 与 resume_generate 都必须带上用户选定的 template，不传会直接报错/返回选版式提示。返回 id、名称、是否 ATS 友好、适用与不适用场景、主题色。',
    parameters: { type: 'object', properties: {}, required: [] },
    output: {
      schema: { type: 'object', additionalProperties: true },
      render: (_args, value) => [{ type: 'text', text: JSON.stringify(value, null, 2) }],
    },
    timeoutMs: 15_000,
    isConcurrencySafe: () => true,
    async execute() {
      const templates = loadTemplates()
      return {
        count: templates.length,
        templates: templates.map((item) => ({
          id: item.id,
          name: item.name,
          atsFriendly: item.atsFriendly,
          pages: item.pages,
          bestFor: item.bestFor,
          avoidFor: item.avoidFor,
          notes: item.notes,
          requiredHints: item.requiredHints || [],
        })),
      }
    },
  })

  register({
    name: 'resume_intake',
    description: [
      '体检一份「还没写完」的简历数据，告诉你这一版式还缺什么、该问用户哪句话。**必须先有用户选定的版式**；不传 template 时会返回三套版式让用户先挑。',
      '返回 missing（逐条给出可以直接问用户的原话 question 与例子 example，required 表示不补会明显缺块）、warnings（内容质量问题）、ready（必填项是否齐）。',
      '用法：用户给的信息还零散时，先把已知部分整理成 resume-spec v2 传进来，按 missing 里的话逐条追问；补齐后 ready=true 再调 resume_generate。',
      '不要替用户填空、不要编造数字；用户说「没有」的项就从数据里去掉，版面会自动收。',
    ].join(''),
    parameters: {
      type: 'object',
      properties: {
        template: { type: 'string', description: '版式 id，来自 resume_template_list。' },
        data: {
          type: 'object',
          description: '已有数据（resume-spec v2，可以残缺，只放已经确认过的内容）。',
          additionalProperties: true,
        },
        dataPath: { type: 'string', description: '已有 JSON 文件路径；与 data 二选一。' },
      },
      required: [],
    },
    output: {
      schema: { type: 'object', additionalProperties: true },
      render: (_args, value) => {
        if (value?.needTemplate) {
          const lines = [value.question || '先定版式：']
          for (const option of value.options || []) {
            lines.push(`· ${option.id}（${option.name}）—— 适合：${option.bestFor}`)
          }
          if (value.nextStep) lines.push(value.nextStep)
          return [{ type: 'text', text: lines.join('\n') }]
        }
        const lines = [`版式：${value.templateName}（${value.template}）`, value.ready ? '必填项已齐，可以生成' : `还差 ${value.blocking} 条必填`]
        for (const item of value.missing) {
          lines.push(`${item.required ? '【必填】' : '【建议】'}${item.key}：${item.question}（例：${item.example}）`)
        }
        for (const warning of value.warnings || []) lines.push(`⚠ ${warning}`)
        lines.push(value.nextStep)
        return [{ type: 'text', text: lines.join('\n') }]
      },
    },
    timeoutMs: 15_000,
    isConcurrencySafe: () => true,
    async execute(args) {
      const templates = loadTemplates()
      const requested = typeof args?.template === 'string' ? args.template.trim() : ''
      let spec = args?.data || {}
      if (typeof spec === 'string') {
        const text = spec.trim()
        if (text.startsWith('{')) spec = JSON.parse(text)
        else if (existsSync(text)) spec = JSON.parse(readFileSync(text, 'utf8'))
        else throw new Error('data 既不是 JSON 也不是已存在的文件路径')
      }
      if (!spec || typeof spec !== 'object') spec = {}
      if (!requested) {
        // 还没选版式：先把三套摆在用户面前，别悄悄用默认值
        return {
          needTemplate: true,
          question: '先定版式再谈缺什么：你投什么岗位？',
          options: templates.map((t) => ({
            id: t.id,
            name: t.name,
            bestFor: t.bestFor?.[0] || '',
            avoidFor: t.avoidFor?.[0] || '',
          })),
          nextStep: '把 options 用一句话摆给用户挑，选完带上 template 再调一次 resume_intake / resume_generate。',
        }
      }
      if (!templates.some((item) => item.id === requested)) {
        throw new Error(`没有这个版式：${requested}（可选：${templates.map((t) => t.id).join('、')}）`)
      }
      return analyze(spec, requested, templates)
    },
  })

  register({
    name: 'resume_generate',
    description: [
      '把结构化的简历数据渲染成可编辑的 Word 简历，并可同时导出 PDF。三套版式：dark-blue（深灰蓝双栏工科）、wine-ribbon（酒红绶带双栏设计）、single-ats（单栏 ATS 网申）。**template 必填**：没选版式会报错并把三套摆出来，不会替你默认。',
      '数据格式见插件目录 engine/spec.md（resume-spec v2）：basics（姓名/英文名/照片/求职意向/基础信息/侧栏小节含技能进度条与能力雷达）+ sections（education/experience/bullets/awards/text，按数组顺序渲染）。',
      '正文支持两种行内标记：**文字** 变加粗，{{文字}} 变强调色。',
      '硬性要求：所有数字、时间、项目必须来自用户本人的输入，绝不替用户编造经历或成果；缺的信息先用 resume_intake 问清楚，不要填 XXXX。',
      '建议流程：resume_template_list 选版式 → 用户零散信息整理成 spec → resume_intake 追问缺口 → 调本工具 → 把 docx/PDF 路径交给用户确认。',
    ].join(''),
    parameters: {
      type: 'object',
      properties: {
        data: {
          type: 'object',
          description: '简历数据对象（resume-spec v2）。与 dataPath 二选一。',
          additionalProperties: true,
        },
        dataPath: { type: 'string', description: '已有 JSON 文件的路径；与 data 二选一。' },
        template: { type: 'string', description: '版式 id，来自 resume_template_list；默认第一个。' },
        outDir: { type: 'string', description: '输出目录（建议放在当前工作区）；默认 $DSH_HOME/resume-out。' },
        fileName: { type: 'string', description: '文件名（不含扩展名），默认用姓名。' },
        pdf: { type: 'boolean', description: '是否同时导出 PDF，默认 true。' },
      },
      required: [],
    },
    output: {
      schema: { type: 'object', additionalProperties: true },
      render: (_args, value) => {
        const lines = [`简历已生成：${value.docx}`]
        if (value.pdf) lines.push(`PDF：${value.pdf}`)
        if (value.pages) {
          const scale = value.layoutScale ? `，正文缩到 ${Math.round(value.layoutScale * 100)}%` : ''
          lines.push(`页数：${value.pages} 页${scale}`)
        }
        for (const warning of value.warnings || []) lines.push(`⚠ ${warning}`)
        return [{ type: 'text', text: lines.join('\n') }]
      },
    },
    timeoutMs: 180_000,
    isConcurrencySafe: () => false,
    async execute(args, exec) {
      const input = { ...args }
      if (!input.data && input.dataPath) input.data = input.dataPath
      return generate(input, exec, config)
    },
  })

  console.log('[dsh-resume] 已注册 resume_template_list / resume_intake / resume_generate')
}
