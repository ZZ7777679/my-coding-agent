/** 沙箱兼容提示和变量名称持久化，不启动项目进程。 Sandbox hints and name persistence without project execution. */
import { mkdir, mkdtemp, readFile } from 'node:fs/promises'
import path from 'node:path'
import { expect, test } from './runtime'
import { artifacts, choose, launch } from './helpers'

test('sandbox settings persist names and explain unavailable local MCP before connecting', async () => {
  await mkdir(artifacts, { recursive: true })
  const root = await mkdtemp(path.join(artifacts, 'desktop-sandbox-settings-'))
  const project = path.join(root, 'project')
  const data = path.join(root, 'data')
  await mkdir(project)
  const app = await launch(data, project)
  try {
    const page = await app.firstWindow()
    await expect(page.getByTestId('connection-status')).toHaveText('本地后端已连接')
    await choose(app, project)
    await page.getByRole('button', { name: '设置与诊断', exact: true }).click()
    const environments = page.getByRole('region', { name: '项目执行环境' })
    await environments.getByLabel('执行方式', { exact: true }).selectOption('sandbox')
    await expect(environments.getByLabel('允许沙箱网络', { exact: true })).toBeChecked()
    await environments.getByText('项目环境变量', { exact: true }).click()
    await environments.getByLabel('显式传入环境变量名称').fill('DATABASE_URL\nCUSTOM_BUILD_HOME')
    await environments.getByRole('button', { name: '保存项目环境', exact: true }).click()
    await expect(
      environments.getByRole('button', { name: '保存项目环境', exact: true })
    ).toBeEnabled()
    const saved = await readFile(path.join(data, 'environments.json'), 'utf8')
    expect(saved).toContain('DATABASE_URL')
    await page.reload()
    await expect(page.getByTestId('connection-status')).toHaveText('本地后端已连接')
    await page.getByRole('button', { name: '设置与诊断', exact: true }).click()
    await expect(environments.getByLabel('执行方式', { exact: true })).toHaveValue('sandbox')
    await environments.getByText('项目环境变量', { exact: true }).click()
    await expect(environments.getByLabel('显式传入环境变量名称')).toHaveValue(
      'DATABASE_URL\nCUSTOM_BUILD_HOME'
    )
    await page.evaluate(async () => {
      const result = await window.agent.saveMcp({
        server: { server_id: 'fixture', name: 'Local fixture', command: 'never-started.exe' }
      })
      if (!result.ok) throw new Error(result.error.message)
    })
    await page.getByRole('button', { name: 'MCP 管理', exact: true }).click()
    const server = page.locator('.mcp-server').filter({ hasText: 'Local fixture' })
    await expect(server).toContainText('当前沙箱暂不支持')
    await server.locator('summary').click()
    await expect(server.getByRole('button', { name: '连接 / 重连', exact: true })).toBeDisabled()
    await expect(server).toContainText('可继续用文件工具、沙箱命令')
    await page.screenshot({ path: path.join(root, 'sandbox-compatibility.png') })
  } finally {
    await app.close()
  }
})
