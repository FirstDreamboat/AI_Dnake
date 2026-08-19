import { defineStore } from 'pinia'
import { authApi } from '@/api'

export interface UserInfo {
  id: number
  username: string
  real_name?: string
  role: string
  // 非管理员为 true 时，登录后必须先修改密码
  must_change_password?: boolean
  permissions?: string[]
}

export const useUserStore = defineStore('user', {
  state: () => ({
    token: localStorage.getItem('access_token') || '',
    userInfo: JSON.parse(localStorage.getItem('user_info') || 'null') as UserInfo | null,
  }),
  getters: {
    isLogin: (state) => !!state.token,
    isAdmin: (state) => state.userInfo?.role === 'admin',
    permissions: (state): string[] => {
      const info = state.userInfo
      if (!info) return []
      if (info.role === 'admin') return []
      return info.permissions || []
    },
  },
  actions: {
    /** 判断当前用户是否拥有指定权限点（admin 恒为 true） */
    hasPerm(code: string): boolean {
      const info = this.userInfo
      if (!info) return false
      if (info.role === 'admin') return true
      return (info.permissions || []).includes(code)
    },
    async login(username: string, password: string, captchaId?: string, captchaCode?: string) {
      const data = await authApi.login({ username, password, captcha_id: captchaId, captcha_code: captchaCode })
      this.token = data.access_token
      this.userInfo = data.user
      localStorage.setItem('access_token', data.access_token)
      localStorage.setItem('user_info', JSON.stringify(data.user))
      return data
    },
    async fetchUser() {
      const info = await authApi.me()
      this.userInfo = info
      localStorage.setItem('user_info', JSON.stringify(info))
    },
    logout() {
      this.token = ''
      this.userInfo = null
      localStorage.removeItem('access_token')
      localStorage.removeItem('user_info')
    },
    /** 修改密码成功后清除强制改密标记 */
    clearMustChangePassword() {
      if (this.userInfo) {
        this.userInfo.must_change_password = false
        localStorage.setItem('user_info', JSON.stringify(this.userInfo))
      }
    },
  },
})
