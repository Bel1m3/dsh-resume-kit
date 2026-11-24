// 插件冒烟测试：不启动 DSH，用桩 ctx 走一遍真实工具调用。
// 覆盖：工具注册、模板列表、三套版式生成（docx+pdf）、缺项体检、占位符告警、照片规则、参数校验。
import { existsSync, readFileSync, rmSync } from 'node:fs'
import { join } from 'node:path'
import { spawnSync } from 'node:child_process'

// 沙箱里禁止创建子进程（spawn EPERM），此时只跑纯逻辑部分
const SANDBOXED = (() => {
  try {
    const r = spawnSync(process.execPath, ['-e', '0'])
    return Boolean(r.error && String(r.error.code) === 'EPERM')
  } catch {
    return false
  }
})()

// 自动探测 DSH 自带的 python；找不到就让插件自己去 PATH 上找，不写死本机路径
const PYTHON = (() => {
  const candidates = [
    process.env.DSH_RESUME_PYTHON,
    join(process.execPath, '..', 'resources', 'office-runtime', 'primary-runtime', 'dependencies', 'python', 'python.exe'),
    join(process.execPath, '..', 'resources', 'office-runtime', 'primary-runtime', 'dependencies', 'python', 'bin', 'python3'),
  ].filter(Boolean)
  return candidates.find((p) => existsSync(p)) || null
})()
const root = process.cwd()
const outDir = join(root, 'out', 'smoke-' + Date.now().toString(36))
const song = JSON.parse(readFileSync(join(root, 'examples', 'spec-song.json'), 'utf8'))
const hu = JSON.parse(readFileSync(join(root, 'examples', 'spec-hu.json'), 'utf8'))

const results = []
const check = (label, ok, detail = '') => {
  results.push({ label, ok })
  console.log(`${ok ? 'PASS' : 'FAIL'}  ${label}${detail ? '  — ' + detail : ''}`)
}

const registered = new Map()
const ctx = {
  tools: {
    register: (definition) => {
      registered.set(definition.name, definition)
    },
  },
  effect: () => () => {},
}

const { apply } = await import('../lib/index.js')
const previousLog = console.log
console.log = () => {}
apply(ctx, PYTHON ? { python: PYTHON } : {})
console.log = previousLog

check('注册了三个工具', registered.size === 3, [...registered.keys()].join(', '))
check('resume_generate 有参数 schema', Boolean(registered.get('resume_generate')?.parameters?.properties?.data))

// 1) 模板列表
const listed = await registered.get('resume_template_list').execute({}, {})
check('模板列表返回三套版式', listed.count === 3, listed.templates?.map((t) => t.id).join(', '))
check('模板带适用/不适用说明', listed.templates.every((t) => Array.isArray(t.bestFor) && Array.isArray(t.avoidFor)))
check('模板带缺项提示', listed.templates.every((t) => Array.isArray(t.requiredHints)))

// 2) 缺项体检
const intake = registered.get('resume_intake')
const partial = await intake.execute({
  template: 'wine-ribbon',
  data: { basics: { name: '张三', fields: [{ label: '电话', value: '13800000000' }] }, sections: [] },
}, {})
check('残缺数据判为未就绪', partial.ready === false, `缺 ${partial.blocking} 条必填`)
check('缺项带可直接追问的原话', (partial.missing || []).every((m) => m.question && m.question.length > 6))
const readyHu = await intake.execute({ template: 'wine-ribbon', data: hu }, {})
check('完整数据判为就绪', readyHu.ready === true, JSON.stringify(readyHu.missing))

// 3) 两套版式各生成一次
const generate = registered.get('resume_generate')
for (const [label, data, template] of [['深灰蓝', song, 'dark-blue'], ['酒红绶带', hu, 'wine-ribbon'], ['单栏ATS', song, 'single-ats']]) {
  if (SANDBOXED) {
    console.log(`SKIP  ${label} 渲染（沙箱内无法起子进程，请在 DSH 宿主或普通终端跑）`)
    continue
  }
  const out = await generate.execute({ data, template, outDir, fileName: 'smoke-' + template }, {})
  check(`${label} 生成 docx`, Boolean(out.docx && existsSync(out.docx)), out.docx)
  check(`${label} 导出 pdf`, Boolean(out.pdf && existsSync(out.pdf)), out.pdf || '（未生成）')
}

// 4) 占位符告警
if (SANDBOXED) {
  console.log('SKIP  占位符告警（沙箱内无法渲染）')
} else {
  const withPlaceholder = JSON.parse(JSON.stringify(song))
  withPlaceholder.sections[1].items[0].blocks[0].text = '负责 XXXX 项目'
  const flagged = await generate.execute({ data: withPlaceholder, template: 'dark-blue', outDir, fileName: 'smoke-ph' }, {})
  check('检测到 XXXX 占位符', (flagged.warnings || []).some((w) => w.includes('占位符')),
    (flagged.warnings || []).find((w) => w.includes('占位符')))
}

// 5) 参数校验
let threwNoTemplate = false
try {
  await generate.execute({ data: song, outDir }, {})
} catch (error) {
  threwNoTemplate = String(error.message).includes('还没选版式') && String(error.message).includes('dark-blue')
}
check('没选版式时拒绝生成并列出可选项', threwNoTemplate)

const intakeNoTemplate = await intake.execute({ data: song }, {})
check('没选版式时 intake 返回三套让用户挑',
  intakeNoTemplate.needTemplate === true && (intakeNoTemplate.options || []).length === 3,
  (intakeNoTemplate.options || []).map((o) => o.id).join(', '))

let threw = false
try {
  await generate.execute({ data: { basics: {} }, template: 'dark-blue', outDir }, {})
} catch (error) {
  threw = String(error.message).includes('basics.name')
}
check('缺姓名时抛出明确错误', threw)

let threwPhoto = false
try {
  const noPhoto = JSON.parse(JSON.stringify(song))
  delete noPhoto.basics.photo
  await generate.execute({ data: noPhoto, template: 'dark-blue', outDir }, {})
} catch (error) {
  threwPhoto = String(error.message).includes('照片')
}
check('双栏版式缺照片时拦下来并提示去要照片', threwPhoto)

let atsNoPhotoOk = false
try {
  const noPhoto = JSON.parse(JSON.stringify(song))
  delete noPhoto.basics.photo
  const out = await generate.execute({ data: noPhoto, template: 'single-ats', outDir, fileName: 'smoke-nophoto' }, {})
  atsNoPhotoOk = Boolean(out.docx && existsSync(out.docx))
} catch (error) {
  // 沙箱里到不了渲染，但只要不是被「照片」规则拦下，就说明放行逻辑是对的
  atsNoPhotoOk = /EPERM|spawn/i.test(String(error.message))
}
check('单栏 ATS 允许不放照片', atsNoPhotoOk)

let threwPhotoPath = false
try {
  const badPhoto = JSON.parse(JSON.stringify(song))
  badPhoto.basics.photo = 'D:/not-exist/me.jpg'
  await generate.execute({ data: badPhoto, template: 'dark-blue', outDir }, {})
} catch (error) {
  threwPhotoPath = String(error.message).includes('找不到这张照片')
}
check('照片路径不存在时报明确错误', threwPhotoPath)

let threwTemplate = false
try {
  await generate.execute({ data: song, outDir, template: 'no-such' }, {})
} catch (error) {
  threwTemplate = String(error.message).includes('没有这个版式')
}
check('未知版式时抛出明确错误', threwTemplate)

try {
  rmSync(outDir, { recursive: true, force: true })
} catch {}

const failed = results.filter((r) => !r.ok)
console.log(`\n${results.length - failed.length}/${results.length} passed`)
if (failed.length) process.exitCode = 1
