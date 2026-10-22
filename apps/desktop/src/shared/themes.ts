import type { AppearanceSettings } from '../generated/protocol'
import defaults from '../../../../src/my_agent/defaults.json'

/** 单一色板供主进程启动背景与 renderer 共用。 Shared startup and renderer palettes. */
export const palettes = {
  graphite: {
    name: '石墨蓝',
    background: '#14161b',
    panel: '#1d212a',
    text: '#e8ecf2',
    accent: '#7aa2f7',
    dark: true
  },
  light: {
    name: '经典浅色',
    background: '#f8fafc',
    panel: '#ffffff',
    text: '#0f172a',
    accent: '#2563eb',
    dark: false
  },
  nord: {
    name: '北欧灰蓝',
    background: '#2e3440',
    panel: '#3b4252',
    text: '#eceff4',
    accent: '#88c0d0',
    dark: true
  },
  paper: {
    name: '暖纸米色',
    background: '#f7f3eb',
    panel: '#fffcf5',
    text: '#40372f',
    accent: '#8a5a36',
    dark: false
  },
  mint: {
    name: '深灰薄荷',
    background: '#141817',
    panel: '#202824',
    text: '#e5ece8',
    accent: '#7bc7a8',
    dark: true
  }
} satisfies Record<
  AppearanceSettings['preset'],
  { name: string; background: string; panel: string; text: string; accent: string; dark: boolean }
>

// JSON 导入会将字符串字面量拓宽；实际偏好在受信 IPC 边界按生成 schema 校验。
// JSON imports widen literals; real preferences are schema-validated at the trusted IPC boundary.
export const defaultAppearance: AppearanceSettings = {
  ...defaults.appearance,
  preset: defaults.appearance.preset as AppearanceSettings['preset']
}

/** 按 sRGB 定义计算相对亮度。 Compute relative sRGB luminance. */
function luminance(hex: string): number {
  const rgb = [1, 3, 5].map((offset) => {
    const value = parseInt(hex.slice(offset, offset + 2), 16) / 255
    return value <= 0.04045 ? value / 12.92 : ((value + 0.055) / 1.055) ** 2.4
  })
  return rgb[0] * 0.2126 + rgb[1] * 0.7152 + rgb[2] * 0.0722
}

/** 按亮度选取主按钮前景。 Choose a readable primary-button foreground. */
export function accentInk(hex: string): string {
  return luminance(hex) > 0.179 ? '#000000' : '#ffffff'
}

/** 对比提示仅用于预览，不拒绝用户配色。 Contrast advice never blocks a chosen palette. */
export function contrastRatio(first: string, second: string): number {
  const a = luminance(first),
    b = luminance(second)
  return (Math.max(a, b) + 0.05) / (Math.min(a, b) + 0.05)
}
