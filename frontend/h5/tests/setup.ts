import { TextDecoder, TextEncoder } from 'node:util'
import { ReadableStream } from 'node:stream/web'
import { afterEach, vi } from 'vitest'
Object.assign(globalThis, { TextDecoder, TextEncoder, ReadableStream })
// jsdom 未实现 ObjectURL API：附件缩略图（blob 转 objectURL）相关测试需要
if (typeof URL.createObjectURL !== 'function') {
  URL.createObjectURL = () => `blob:jsdom-mock-${Math.random().toString(36).slice(2)}`
  URL.revokeObjectURL = () => {}
}
for (const name of ['localStorage', 'sessionStorage']) {
  const entries = new Map<string, string>()
  const storage = { getItem: (key: string) => entries.get(key) ?? null, setItem: (key: string, value: string) => entries.set(key, String(value)), removeItem: (key: string) => entries.delete(key), clear: () => entries.clear() }
  Object.defineProperty(globalThis, name, { configurable: true, value: storage })
}
afterEach(() => { localStorage.clear(); sessionStorage.clear(); vi.unstubAllGlobals() })
