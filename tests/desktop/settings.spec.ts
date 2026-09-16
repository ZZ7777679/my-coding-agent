/**
 * 设置与诊断的桌面验收；网络 UI 使用模拟报告，其余指定本机探测实际执行。
 * Desktop settings checks; network UI uses a mock report while selected local probes run.
 */

import { expect, test } from './runtime'
import { artifacts, sentinel, launch, choose, exportTarget, workspaceFixture } from './helpers'
import { access, mkdir, mkdtemp, readFile, readdir, symlink, writeFile } from 'node:fs/promises'
import path from 'node:path'

/**
 * 验证模型保存与重启、只读诊断及公开导出的取消和失败保护。
 * Verify model persistence, read-only diagnostics and export cancellation/failure protection.
 */
test('model settings persist, local diagnostics stay read-only, and JSON exports remain public', async () => {
  await mkdir(artifacts, { recursive: true })
  const root = await mkdtemp(path.join(artifacts, 'desktop-settings-'))
  const dataDir = path.join(root, 'data')
  const project = path.join(root, '中文 项目')
  await mkdir(project)
  const workspace = await workspaceFixture(root, dataDir, project)
  let app = await launch(dataDir, project, workspace)
  try {
    let page = await app.firstWindow()
    await expect(page.getByTestId('connection-status')).toHaveText('本地后端已连接')
    await choose(app, project)
    const projectsBefore = await readFile(path.join(dataDir, 'projects.json'), 'utf8')
    await page.getByRole('button', { name: '设置与诊断', exact: true }).click()
    await expect(page.getByLabel('默认模型')).toHaveValue('glm-5.3-flash')
    await expect(page.locator('#default-model option')).toHaveCount(2)
    await expect(page.getByLabel('探测服务网络连通性')).not.toBeChecked()
    await expect(page.getByLabel('实际测试数据目录写入')).not.toBeChecked()
    await expect(page.getByTestId('diagnostic-report')).toHaveCount(0)
    const connections = page.getByRole('region', { name: '模型连接池', exact: true })
    const glm = connections.getByTestId('model-connection-glm-5.3-flash')
    const deepseek = connections.getByTestId('model-connection-deepseek-v4.1-flash')
    await expect(glm).toContainText('尚未测试')
    await expect(deepseek).toContainText('尚未测试')
    await expect(connections.getByTestId('connection-pool-status')).toContainText(
      '共享客户端：未创建'
    )
    await connections.getByLabel('跨会话复用连接').uncheck()
    await connections.getByLabel('连接测试超时（秒）').fill('7.5')
    await connections.getByRole('button', { name: '保存连接设置', exact: true }).click()
    await expect(connections).toContainText('连接设置已保存')
    await expect(connections.getByTestId('connection-pool-status')).toContainText('当前复用：关闭')

    // 仅模拟网络探测结果的 UI 展示；真实池生命周期由本地 HTTP 用例验证。
    // Mock probe presentation only; local HTTP tests verify the actual pool lifecycle.
    const pool = await page.evaluate(() => window.agent.getConnections())
    if (!pool.ok) throw new Error('Missing pool status')
    await app.evaluate(({ ipcMain }, state) => {
      ipcMain.removeHandler('agent:test-connection')
      ipcMain.handle('agent:test-connection', (_event, params) => {
        process.env.MY_AGENT_TEST_CONNECTION_PARAMS = JSON.stringify(params)
        return {
          ok: true,
          data: {
            ...state,
            last_probe: {
              finished_at: new Date().toISOString(),
              code: 'OK',
              http_status: 200,
              models_confirmed: true,
              progress: {
                phase: 'completed',
                elapsed_ms: 35,
                connect_ms: 5,
                tls_ms: 8,
                response_headers_ms: 30,
                response_complete: true
              }
            }
          }
        }
      })
    }, pool.data)
    await connections.getByText('网关目录探测与最近请求', { exact: true }).click()
    await connections.getByRole('button', { name: '网关目录探测', exact: true }).click()
    await expect(connections).toContainText('HTTP 200')
    expect(
      await app.evaluate(() => JSON.parse(process.env.MY_AGENT_TEST_CONNECTION_PARAMS ?? '{}'))
    ).toEqual({ timeout_seconds: 7.5 })
    await connections.screenshot({ path: path.join(root, 'connection-pool.png') })
    await connections.getByRole('button', { name: '释放已有连接', exact: true }).click()
    await expect(connections).toContainText('已有连接已释放')
    // 模拟两个不同结果以验证目标传参和行归属；生产请求由 Python SSE 用例覆盖。
    // Simulate distinct outcomes for target/row attribution; Python covers production requests.
    await app.evaluate(({ ipcMain }, state) => {
      ipcMain.removeHandler('agent:test-model-connection')
      ipcMain.handle('agent:test-model-connection', (_event, params) => {
        process.env.MY_AGENT_TEST_MODEL_PARAMS = JSON.stringify(params)
        const success = params.model_id === 'glm-5.3-flash'
        state.models = (state.models ?? []).map((row) =>
          row.model_id !== params.model_id
            ? row
            : {
                ...row,
                last_test: {
                  finished_at: new Date().toISOString(),
                  code: success ? 'OK' : 'MODEL_TIMEOUT',
                  message: success ? '该模型已返回完整文本响应。' : '模型测试超过设定等待时间。',
                  remediation: success ? '' : '查看停止阶段后重试。',
                  progress: {
                    phase: success ? 'completed' : 'tls',
                    elapsed_ms: success ? 1400 : 7500,
                    first_text_ms: success ? 1200 : null
                  },
                  usage: null
                }
              }
        )
        return { ok: true, data: state }
      })
    }, pool.data)
    await glm.getByRole('button', { name: '测试 GLM', exact: true }).click()
    await expect(glm).toContainText('最近测试成功')
    await expect(glm).toContainText('1.200 秒')
    await expect(deepseek).toContainText('尚未测试')
    expect(
      await app.evaluate(() => JSON.parse(process.env.MY_AGENT_TEST_MODEL_PARAMS ?? '{}'))
    ).toEqual({ model_id: 'glm-5.3-flash', timeout_seconds: 7.5 })
    await deepseek.getByRole('button', { name: '测试 DeepSeek', exact: true }).click()
    await expect(deepseek).toContainText('最近测试失败 · MODEL_TIMEOUT')
    await expect(deepseek).toContainText('模型首字 未观测')
    await expect(glm).toContainText('最近测试成功')
    await expect(glm).toContainText('1.200 秒')
    expect(
      await app.evaluate(() => JSON.parse(process.env.MY_AGENT_TEST_MODEL_PARAMS ?? '{}'))
    ).toEqual({ model_id: 'deepseek-v4.1-flash', timeout_seconds: 7.5 })
    await connections.getByText('网关目录探测与最近请求', { exact: true }).click()
    await connections.screenshot({ path: path.join(root, 'model-connections.png') })
    await writeFile(
      path.join(root, 'connection-probe-ui-simulated.txt'),
      'Catalog and per-model UI results simulated; no external network or model request was sent.\n'
    )
    await page.getByLabel('默认模型').selectOption('deepseek-v4.1-flash')
    await page.getByRole('button', { name: '保存默认模型', exact: true }).click()
    await expect(page.getByRole('status')).toContainText('默认模型已保存')
    const configBefore = await readFile(path.join(dataDir, 'config.toml'), 'utf8')
    expect(configBefore).toContain('deepseek-v4.1-flash')
    expect(configBefore).toContain('reuse_enabled = false')
    expect(configBefore).not.toContain(sentinel)
    const malformed = await page.evaluate(() =>
      window.agent.saveConfig(JSON.parse('{"model_id":"glm-5.3-flash","api_key":"untrusted"}'))
    )
    expect(malformed.ok).toBe(false)
    expect(await readFile(path.join(dataDir, 'config.toml'), 'utf8')).toBe(configBefore)

    await page.getByRole('button', { name: '运行诊断', exact: true }).click()
    await expect(page.getByTestId('diagnostic-report')).toContainText('本次检查已完成')
    await expect(page.locator('[data-check-id="write_probe"]')).toContainText('未执行写入探测')
    await expect(page.getByTestId('diagnostic-report')).toContainText('模型认证：未验证')
    expect(await readFile(path.join(dataDir, 'projects.json'), 'utf8')).toBe(projectsBefore)
    expect(await readFile(path.join(dataDir, 'config.toml'), 'utf8')).toBe(configBefore)

    for (const [kind, label] of [
      ['config', '导出配置 JSON'],
      ['projects', '导出项目 JSON'],
      ['diagnostics', '导出诊断 JSON']
    ]) {
      const target = path.join(root, kind + '.json')
      await exportTarget(app, target)
      await page.getByRole('button', { name: label, exact: true }).click()
      await expect(page.getByRole('status')).toContainText(target)
      const content = await readFile(target, 'utf8')
      expect(content).not.toContain(sentinel)
      const value = JSON.parse(content)
      if (kind === 'config') expect(value.model_id).toBe('deepseek-v4.1-flash')
      if (kind === 'projects') expect(value.active_project.path).toBe(project)
      if (kind === 'diagnostics') expect(value.mode).toEqual(['local'])
    }
    await exportTarget(app, null)
    await page.getByRole('button', { name: '导出配置 JSON', exact: true }).click()
    await expect(page.getByRole('status')).toContainText('已取消导出')
    await exportTarget(app, path.join(dataDir, 'projects.json'))
    await page.getByRole('button', { name: '导出配置 JSON', exact: true }).click()
    await expect(page.getByRole('alert')).toContainText('JSON 导出失败')
    expect(await readFile(path.join(dataDir, 'projects.json'), 'utf8')).toBe(projectsBefore)
    await exportTarget(app, path.join(root, 'config-retry.json'))
    await page.getByRole('button', { name: '导出配置 JSON', exact: true }).click()
    await expect(page.getByRole('status')).toContainText('config-retry.json')
    expect((await readdir(root)).filter((name) => name.endsWith('.tmp'))).toEqual([])
    await page.getByRole('heading', { name: '设置与诊断', exact: true }).scrollIntoViewIfNeeded()
    await page.screenshot({ path: path.join(root, 'settings.png') })
    await app.close()

    app = await launch(dataDir, project, workspace)
    page = await app.firstWindow()
    await expect(page.getByTestId('active-project-path')).toHaveText(project)
    await page.getByRole('button', { name: '设置与诊断', exact: true }).click()
    await expect(page.getByLabel('默认模型')).toHaveValue('deepseek-v4.1-flash')
    await expect(page.getByLabel('跨会话复用连接')).not.toBeChecked()
    await expect(page.getByLabel('连接测试超时（秒）')).toHaveValue('7.5')
    await page.getByRole('button', { name: '刷新配置', exact: true }).click()
    await expect(page.getByRole('status')).toContainText('配置已刷新')
    expect(await page.locator('body').innerText()).not.toContain(sentinel)
    await app.evaluate(({ BrowserWindow }) => {
      BrowserWindow.getAllWindows()[0].setSize(960, 700)
    })
    await page.screenshot({ path: path.join(root, 'settings-narrow.png') })
    expect(
      await page
        .locator('.workspace')
        .evaluate((element) => element.scrollWidth <= element.clientWidth)
    ).toBe(true)
  } finally {
    await app.close()
  }
})

/**
 * 验证目录配置边界和重载恢复，同时确认当前数据未被迁移。
 * Verify startup-path validation and reload recovery without moving active data.
 */
test('startup directory edits are validated, saved for restart, and leave active data in place', async () => {
  await mkdir(artifacts, { recursive: true })
  const root = await mkdtemp(path.join(artifacts, 'desktop-paths-'))
  const dataDir = path.join(root, 'data')
  const project = path.join(root, 'project')
  const nextProject = path.join(root, '下次项目')
  const nextData = path.join(root, '下次数据')
  await mkdir(project)
  await mkdir(nextProject)
  const workspace = await workspaceFixture(root, dataDir, project)
  const localFile = path.join(workspace, 'agent.paths.local.json')
  const app = await launch(dataDir, project, workspace)
  try {
    const page = await app.firstWindow()
    await expect(page.getByTestId('connection-status')).toHaveText('本地后端已连接')
    await choose(app, project)
    const projectsBefore = await readFile(path.join(dataDir, 'projects.json'), 'utf8')
    await page.getByRole('button', { name: '设置与诊断', exact: true }).click()
    await expect(page.getByLabel('应用数据目录')).toHaveValue(dataDir)
    const before = await readFile(localFile, 'utf8')
    await app.evaluate(({ dialog }) => {
      dialog.showOpenDialog = async () => ({ canceled: true, filePaths: [] })
    })
    await page.getByRole('button', { name: '选择数据目录', exact: true }).click()
    await expect(page.getByRole('button', { name: '选择数据目录', exact: true })).toBeEnabled()
    await expect(page.getByLabel('应用数据目录')).toHaveValue(dataDir)
    expect(await readFile(localFile, 'utf8')).toBe(before)

    await page.getByLabel('应用数据目录').fill(project)
    await page.getByRole('button', { name: '保存启动目录', exact: true }).click()
    await expect(page.getByRole('alert')).toContainText('启动目录保存失败')
    expect(await readFile(localFile, 'utf8')).toBe(before)
    const junction = path.join(root, 'project-junction')
    await symlink(project, junction, 'junction')
    const overlap = await page.evaluate(
      async (location) => window.agent.saveStartupPaths(location),
      {
        data_dir: path.join(junction, 'nested-data'),
        project_dir: project
      }
    )
    expect(overlap.ok).toBe(false)
    expect(await readFile(localFile, 'utf8')).toBe(before)

    await page.getByLabel('应用数据目录').fill(nextData)
    await app.evaluate(({ dialog }, selected) => {
      dialog.showOpenDialog = async () => ({ canceled: false, filePaths: [selected] })
    }, nextProject)
    await page.getByRole('button', { name: '选择起始目录', exact: true }).click()
    await expect(page.getByLabel('项目选择器起始目录')).toHaveValue(nextProject)
    await page.getByRole('button', { name: '保存启动目录', exact: true }).click()
    await expect(page.getByRole('status')).toContainText('重新启动后生效')
    expect(JSON.parse(await readFile(localFile, 'utf8'))).toEqual({
      data_dir: nextData,
      project_dir: nextProject
    })
    expect(
      await access(nextData).then(
        () => true,
        () => false
      )
    ).toBe(false)
    expect(await readFile(path.join(dataDir, 'projects.json'), 'utf8')).toBe(projectsBefore)
    const current = await page.evaluate(() => window.agent.getStartupPaths())
    expect(current).toMatchObject({
      ok: true,
      data: { current_data_dir: dataDir, data_dir: nextData }
    })
    await page.reload()
    await page.getByRole('button', { name: '设置与诊断', exact: true }).click()
    await expect(page.getByLabel('应用数据目录')).toHaveValue(nextData)
    await expect(page.getByLabel('项目选择器起始目录')).toHaveValue(nextProject)
    await page.getByRole('button', { name: '项目工作台', exact: true }).click()
    await expect(page.getByTestId('active-project-path')).toHaveText(project)
  } finally {
    await app.close()
  }
})

/**
 * 执行本机开发与写入诊断，再用受控网络报告单独验证选项传递。
 * Run developer/write diagnostics, then verify network option dispatch with a controlled report.
 */
test('development and write diagnostics are real; optional network dispatch uses a controlled response', async () => {
  test.setTimeout(90000)
  await mkdir(artifacts, { recursive: true })
  const root = await mkdtemp(path.join(artifacts, 'desktop-diagnostics-'))
  const dataDir = path.join(root, 'data')
  const project = path.join(root, 'project')
  await mkdir(project)
  const workspace = await workspaceFixture(root, dataDir, project)
  const app = await launch(dataDir, project, workspace)
  try {
    const page = await app.firstWindow()
    await expect(page.getByTestId('connection-status')).toHaveText('本地后端已连接')
    const before = await readFile(path.join(dataDir, 'projects.json'), 'utf8')
    await page.getByRole('button', { name: '设置与诊断', exact: true }).click()
    await page.getByLabel('包括开发工具与容器环境').check()
    await page.getByLabel('实际测试数据目录写入').check()
    await page.getByRole('button', { name: '运行诊断', exact: true }).click()
    await expect(page.locator('[data-check-id="write_probe"]')).toContainText('正常', {
      timeout: 65000
    })
    await expect(page.locator('[data-check-id="node"]')).toBeVisible()
    await expect(page.getByTestId('connection-status')).toHaveText('本地后端已连接')
    expect(await readFile(path.join(dataDir, 'projects.json'), 'utf8')).toBe(before)
    const reportFile = path.join(root, 'developer-report.json')
    await exportTarget(app, reportFile)
    await page.getByRole('button', { name: '导出诊断 JSON', exact: true }).click()
    await expect(page.getByRole('status')).toContainText(reportFile)
    const report = JSON.parse(await readFile(reportFile, 'utf8'))
    expect(report.mode).toEqual(['local', 'dev', 'write_probe'])
    expect(report.catalog_reachable).toBe('not_checked')
    expect((await readdir(dataDir)).filter((name) => name.endsWith('.tmp'))).toEqual([])
    await page.getByRole('heading', { name: '环境诊断', exact: true }).scrollIntoViewIfNeeded()
    await page.screenshot({ path: path.join(root, 'diagnostics.png') })

    // 这里只验证网络选项传递；实际请求边界由 Python 的受控响应测试覆盖。
    // Check network option dispatch here; Python tests the request boundary with controlled responses.
    await app.evaluate(({ ipcMain }, result) => {
      ipcMain.removeHandler('agent:diagnostics')
      ipcMain.handle('agent:diagnostics', async (_event, params) => {
        process.env.MY_AGENT_TEST_DIAGNOSTIC_PARAMS = JSON.stringify(params)
        return {
          ok: true,
          data: { ...result, mode: ['local', 'network'], catalog_reachable: 'error' }
        }
      })
    }, report)
    await page.getByLabel('包括开发工具与容器环境').uncheck()
    await page.getByLabel('实际测试数据目录写入').uncheck()
    await page.getByLabel('探测服务网络连通性').check()
    await page.getByRole('button', { name: '运行诊断', exact: true }).click()
    await expect(page.getByRole('button', { name: '运行诊断', exact: true })).toBeEnabled()
    expect(
      await app.evaluate(() => JSON.parse(process.env.MY_AGENT_TEST_DIAGNOSTIC_PARAMS ?? '{}'))
    ).toEqual({
      dev: false,
      network: true,
      write_probe: false,
      network_timeout_seconds: 20
    })
    expect(await page.locator('body').innerText()).not.toContain(sentinel)
    await writeFile(
      path.join(root, 'network-ui-simulated.txt'),
      'Network UI dispatch only; no provider request was sent.\n'
    )
  } finally {
    await app.close()
  }
})
