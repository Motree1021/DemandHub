// 五区展示元数据：术语保留为结果展示标签，附白话注释，用户无需理解即可使用（对齐原型 formCard 分区）
export interface ZoneMeta { zone: 'A' | 'B' | 'C' | 'D'; title: string; note: string }
export const ZONE_META: readonly ZoneMeta[] = [
  { zone: 'A', title: 'A · 公共要素', note: '基本信息' },
  { zone: 'B', title: 'B · 业务需求', note: '为什么做、价值是什么' },
  { zone: 'C', title: 'C · 用户需求', note: '谁用、用来做什么' },
  { zone: 'D', title: 'D · 功能需求', note: '系统要做什么' },
] as const
