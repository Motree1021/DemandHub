import { TextDecoder, TextEncoder } from 'node:util'
import { ReadableStream } from 'node:stream/web'
import { afterEach, vi } from 'vitest'
Object.assign(globalThis, { TextDecoder, TextEncoder, ReadableStream })
for (const name of ['localStorage', 'sessionStorage']) {
  const entries = new Map<string, string>()
  const storage = { getItem: (key: string) => entries.get(key) ?? null, setItem: (key: string, value: string) => entries.set(key, String(value)), removeItem: (key: string) => entries.delete(key), clear: () => entries.clear() }
  Object.defineProperty(globalThis, name, { configurable: true, value: storage })
}
afterEach(() => { localStorage.clear(); sessionStorage.clear(); vi.unstubAllGlobals() })
