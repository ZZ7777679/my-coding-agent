/**
 * 为共用 JavaScript 启动解析器提供静态类型，行为校验仍在实现中完成。
 * Type the shared JavaScript launch parser; runtime checks remain in its implementation.
 */

/**
 * 描述启动解析器返回的公开配置异常。
 * Describe public configuration errors from the launch parser.
 */
export class LaunchConfigError extends Error {}
/**
 * 描述明确保存的本机数据目录与选择器起始目录。
 * Describe saved local data and picker-start directories.
 */
export interface LocalPaths {
  data_dir: string
  project_dir: string
}
/**
 * 读取存在的字段，缺失字段由启动装配补默认值。
 * Read present fields; launch assembly supplies defaults for missing fields.
 */
export function readLocalPaths(root: string): Partial<LocalPaths>
/**
 * 原子保存完整目录设置，保留损坏的已有文件。
 * Atomically save complete paths, preserving a corrupt existing file.
 */
export function saveLocalPaths(root: string, paths: LocalPaths): void
/**
 * 返回应用实际启动的数据目录与项目选择器起始位置。
 * Return launch data and project-picker directories after resolving priorities.
 */
export function resolveLaunchPaths(
  root: string,
  defaults: {
    data_dir: string
    data_dir_env: string
    project_dir_env: string
    development_project_dir: string
  },
  args: string[],
  env?: Record<string, string | undefined>
): { dataDir: string; projectDir: string }
