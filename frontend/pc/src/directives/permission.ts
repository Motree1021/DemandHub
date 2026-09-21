import type { App, Directive, DirectiveBinding } from 'vue'
import { useUserStore } from '@/store/modules/user'

function hasRole(binding: DirectiveBinding<string | string[]>): boolean {
  const userStore = useUserStore()
  const need = Array.isArray(binding.value) ? binding.value : [binding.value]
  if (!need.length || !need[0]) {
    return true
  }
  return need.some((r) => userStore.roles.includes(r))
}

/**
 * v-role="'ADMIN'" 或 v-role="['ADMIN','EXECUTIVE']"
 * 当前用户不具备任一指定角色时移除元素。
 */
const roleDirective: Directive<HTMLElement, string | string[]> = {
  mounted(el, binding) {
    if (!hasRole(binding)) {
      el.parentNode?.removeChild(el)
    }
  }
}

/**
 * v-action="'ASSIGN'" 配合需求详情 availableActions 使用：
 * 元素上需通过指令值传入动作 key，动作不在可用列表时移除元素。
 * 用法：v-action="['ASSIGN', detail.availableActions]"
 */
const actionDirective: Directive<HTMLElement, [string, string[]]> = {
  mounted(el, binding) {
    const [action, available] = binding.value || []
    if (!action || !Array.isArray(available) || !available.includes(action)) {
      el.parentNode?.removeChild(el)
    }
  }
}

export function setupPermissionDirectives(app: App) {
  app.directive('role', roleDirective)
  app.directive('action', actionDirective)
}
