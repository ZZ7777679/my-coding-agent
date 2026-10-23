/** 真实桌面读取原诊断并带准确范围进入调查。 Read original diagnostics and enter scoped review in Electron. */
import { electron, expect, test } from './runtime'
import { artifacts, choose, sentinel } from './helpers'
import { mkdir, mkdtemp } from 'node:fs/promises'
import path from 'node:path'

test('failure details remain readable and review keeps the selected run', async () => {
  await mkdir(artifacts, { recursive: true })
  const root = await mkdtemp(path.join(artifacts, 'exception-desktop-'))
  const project = path.join(root, 'project')
  await mkdir(project)
  const env: Record<string, string> = { OPENCODE_API_KEY: sentinel, MY_AGENT_PROJECT_DIR: project }
  for (const [name, value] of Object.entries(process.env))
    if (value !== undefined && !(name in env)) env[name] = value
  delete env.ELECTRON_RUN_AS_NODE
  delete env.ELECTRON_RENDERER_URL
  const app = await electron.launch({
    args: [
      path.resolve(__dirname, '../support/desktop_peer.cjs'),
      '--data-dir',
      path.join(root, 'data')
    ],
    env
  })
  try {
    const page = await app.firstWindow()
    await expect(page.getByTestId('connection-status')).toHaveText('本地后端已连接')
    await choose(app, project)
    await page.getByRole('button', { name: '新建任务 →', exact: true }).click()
    await page.getByLabel('阶段目标', { exact: true }).fill('异常与恢复 · 隔离样本')
    await page.getByRole('button', { name: '创建任务与首会话', exact: true }).click()
    await page.getByRole('button', { name: '打开 / 补齐首会话', exact: true }).click()
    await page.getByLabel('输入问题').fill('network: wait headers')
    await page.getByRole('button', { name: '发送', exact: true }).click()
    await expect(page.locator('.compact-model-progress')).toContainText(
      '等待服务响应（尚无响应头）'
    )
    await page.locator('.run-metrics > summary').click()
    await expect(page.getByTestId('model-progress')).toContainText('本次请求总时限 180 秒')
    await expect(page.getByTestId('model-progress')).toContainText('剩余约')
    await page.screenshot({ path: path.join(root, 'waiting-response-headers.png') })
    await page.getByRole('button', { name: '停止运行', exact: true }).click()
    await expect(page.getByTestId('run-status')).toContainText('已停止')
    await page.getByLabel('输入问题').fill('exception: inspect cause')
    await expect(page.getByRole('button', { name: '发送', exact: true })).toBeEnabled()
    await page.getByRole('button', { name: '发送', exact: true }).click()
    await expect(page.getByTestId('run-status')).toContainText('运行失败')
    const notice = page.locator('.failure-notice').filter({ hasText: 'HTTP 400' })
    await notice.getByText('具体原因与调用位置', { exact: true }).click()
    await expect(notice).toContainText('Fixture missing tool response')
    await expect(notice).not.toContainText('isolated-private-value')
    await notice.getByText('代码位置', { exact: true }).last().click()
    await expect(notice).toContainText('agent_peer.py')
    await page.screenshot({ path: path.join(root, 'concrete-cause.png') })
    await page.getByRole('button', { name: '关闭诊断', exact: true }).click()
    await expect(
      notice.getByText('Fixture missing tool response', { exact: false })
    ).not.toBeVisible()
    await page.getByLabel('输入问题').fill('m3: lookup')
    await expect(page.getByRole('button', { name: '发送', exact: true })).toBeEnabled()
    const sid = await page.locator('.tree-session.selected').getAttribute('data-session-id')
    const view = await page.evaluate(async (id) => {
      if (!id) throw new Error('Missing session')
      const reply = await window.agent.getSession({ session_id: id, before_seq: null })
      if (!reply.ok) throw new Error(reply.error.message)
      return reply.data
    }, sid)
    await notice.getByRole('button', { name: '调查这次失败', exact: true }).click()
    await expect(page.locator('.evolution')).toContainText(view.summary.run!.diagnostic_id!)
    await expect(page.getByRole('button', { name: '开始改进', exact: true })).toBeVisible()
    await page.screenshot({ path: path.join(root, 'scoped-investigation.png') })
  } finally {
    await app.close()
  }
})
