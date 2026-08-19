import axios from 'axios'
import type { AxiosRequestConfig } from 'axios'
import { ElMessage } from 'element-plus'

// 统一 axios 实例
const request = axios.create({
  baseURL: '/api/v1',
  timeout: 30000,
})

// 请求拦截器：携带 Token
request.interceptors.request.use((config) => {
  const token = localStorage.getItem('access_token')
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

// 响应拦截器：统一处理业务码
request.interceptors.response.use(
  (response) => {
    const res = response.data
    if (res && typeof res.code !== 'undefined' && res.code !== 0) {
      ElMessage.error(res.message || '请求失败')
      return Promise.reject(new Error(res.message))
    }
    return res?.data ?? res
  },
  (error) => {
    const status = error.response?.status
    let msg = error.response?.data?.message
    if (!msg) {
      // FastAPI 422 校验错误：detail 为数组，提取各字段提示
      const detail = error.response?.data?.detail
      if (Array.isArray(detail) && detail.length) {
        msg = detail
          .map((d: any) => (d.msg ? `${d.loc?.at(-1) ?? ''} ${d.msg}`.trim() : ''))
          .filter(Boolean)
          .join('；')
      }
    }
    if (status === 401) {
      if (msg) ElMessage.error(msg)
      // Token 过期，跳转登录
      localStorage.removeItem('access_token')
      localStorage.removeItem('user_info')
      if (window.location.pathname !== '/login') {
        window.location.href = '/login'
      }
    } else {
      ElMessage.error(msg || error.message || '网络错误')
    }
    return Promise.reject(error)
  },
)

// 响应拦截器已在运行时将返回值解包为业务数据（res.data），
// 这里覆写导出类型，使各 API 方法在 TS 中直接得到解包后的数据类型。
export default request as unknown as {
  get<T = any>(url: string, config?: AxiosRequestConfig): Promise<T>
  post<T = any>(url: string, data?: any, config?: AxiosRequestConfig): Promise<T>
  put<T = any>(url: string, data?: any, config?: AxiosRequestConfig): Promise<T>
  delete<T = any>(url: string, config?: AxiosRequestConfig): Promise<T>
}
