import { createRouter, createWebHistory } from 'vue-router'
import type { RouteRecordRaw } from 'vue-router'

const routes: RouteRecordRaw[] = [
  {
    path: '/login',
    name: 'Login',
    component: () => import('@/views/Login.vue'),
  },
  {
    path: '/change-password',
    name: 'ChangePassword',
    component: () => import('@/views/ChangePassword.vue'),
  },
  {
    path: '/',
    component: () => import('@/views/Layout.vue'),
    redirect: '/dashboard',
    children: [
      { path: 'dashboard', name: 'Dashboard', component: () => import('@/views/Dashboard.vue'), meta: { title: '工作台' } },
      { path: 'projects', name: 'Projects', component: () => import('@/views/Projects.vue'), meta: { title: '项目管理', perm: 'project' } },
      { path: 'projects/:id/documents', name: 'Documents', component: () => import('@/views/Documents.vue'), meta: { title: '需求文档', perm: 'project' } },
      { path: 'projects/:id/test-points', name: 'TestPoints', component: () => import('@/views/TestPoints.vue'), meta: { title: '测试点管理', perm: 'project' } },
      { path: 'projects/:id/cases', name: 'TestCases', component: () => import('@/views/TestCases.vue'), meta: { title: '测试用例', perm: 'project' } },
      { path: 'generate', name: 'Generate', component: () => import('@/views/Generate.vue'), meta: { title: 'AI生成', perm: 'generate' } },
      { path: 'tasks', name: 'Tasks', component: () => import('@/views/Tasks.vue'), meta: { title: '任务历史' } },
      { path: 'knowledge', name: 'Knowledge', component: () => import('@/views/Knowledge.vue'), meta: { title: '知识库', perm: 'knowledge' } },
      { path: 'scripts', name: 'Scripts', component: () => import('@/views/Scripts.vue'), meta: { title: '脚本管理', perm: 'script' } },
      { path: 'script-templates', name: 'ScriptTemplates', component: () => import('@/views/ScriptTemplates.vue'), meta: { title: '脚本模板', perm: 'script_template' } },
      { path: 'statistics', name: 'Statistics', component: () => import('@/views/Statistics.vue'), meta: { title: '统计报表', perm: 'statistics' } },
      { path: 'logs', name: 'Logs', component: () => import('@/views/Logs.vue'), meta: { title: '操作日志', perm: 'logs' } },
      { path: 'settings', name: 'Settings', component: () => import('@/views/Settings.vue'), meta: { title: '系统设置', perm: 'settings' } },
      { path: 'users', name: 'Users', component: () => import('@/views/Users.vue'), meta: { title: '成员管理', perm: 'user_manage' } },
    ],
  },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

// 权限点判断：admin 恒有全部权限
function hasPerm(perms: string[] | undefined, role: string | undefined, code: string): boolean {
  if (role === 'admin') return true
  return (perms || []).includes(code)
}

// 全局路由守卫：未登录跳转登录页；首次登录强制改密；无对应权限点则回到工作台
router.beforeEach((to) => {
  const token = localStorage.getItem('access_token')
  if (to.path !== '/login' && to.path !== '/change-password' && !token) {
    return { path: '/login' }
  }
  let info: any = null
  try {
    info = JSON.parse(localStorage.getItem('user_info') || 'null')
  } catch {
    info = null
  }
  // 非管理员且需强制改密（首次登录 / 密码被重置）
  const needChange = !!token && !!info && info.role !== 'admin' && !!info.must_change_password
  if (to.path === '/login') {
    if (!token) return true
    return needChange ? { path: '/change-password' } : { path: '/' }
  }
  if (needChange && to.path !== '/change-password') {
    return { path: '/change-password' }
  }
  if (!needChange && to.path === '/change-password') {
    return { path: '/' }
  }
  const perm = to.meta.perm as string | undefined
  if (perm && !hasPerm(info?.permissions, info?.role, perm)) {
    return { path: '/' }
  }
  return true
})

export default router
