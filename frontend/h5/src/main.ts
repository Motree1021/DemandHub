import { createApp } from 'vue'
import { createPinia } from 'pinia'
import Vant from 'vant'
import 'vant/lib/index.css'
import './styles/global.css'
import App from './App.vue'
import router from './router'
import { useUserStore } from './store/user'

const app = createApp(App)

app.use(createPinia())
app.use(router)
app.use(Vant)

window.addEventListener('demandhub:unauthorized', () => {
  useUserStore().clear()
  if (router.currentRoute.value.path !== '/auth') router.replace({ path: '/auth', query: { error: '登录已过期，请从创金零售重新进入' } })
})

app.mount('#app')
