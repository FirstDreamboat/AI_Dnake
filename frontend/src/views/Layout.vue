<template>
  <el-container class="layout">
    <el-aside width="220px" class="aside">
      <div class="logo">
        <el-icon :size="22" color="#409EFF"><Cpu /></el-icon>
        <span>AI用例生成平台</span>
      </div>
      <el-menu :default-active="route.path" router background-color="#001529" text-color="#b7c3d9" active-text-color="#409EFF">
        <el-menu-item v-for="item in visibleMenus" :key="item.path" :index="item.path">
          <el-icon><component :is="item.icon" /></el-icon><span>{{ item.title }}</span>
        </el-menu-item>
      </el-menu>
    </el-aside>

    <el-container>
      <el-header class="header">
        <div class="header-title">{{ route.meta.title || '' }}</div>
        <el-dropdown @command="handleCommand">
          <span class="user-info">
            <el-icon><UserFilled /></el-icon>
            {{ userStore.userInfo?.real_name || userStore.userInfo?.username }}
            <el-icon><ArrowDown /></el-icon>
          </span>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item disabled>{{ roleLabel }}</el-dropdown-item>
              <el-dropdown-item divided command="logout">退出登录</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
      </el-header>
      <el-main class="main">
        <router-view />
      </el-main>
    </el-container>
  </el-container>
</template>

<script setup lang="ts">
import { useRoute, useRouter } from 'vue-router'
import { useUserStore } from '@/stores/user'
import { computed } from 'vue'
import { Odometer, Folder, MagicStick, Collection, Document, Setting, User, TrendCharts, Files, Memo } from '@element-plus/icons-vue'

const route = useRoute()
const router = useRouter()
const userStore = useUserStore()

const roleLabel = computed(() => {
  const role = userStore.userInfo?.role
  return { admin: '管理员', manager: '项目经理', engineer: '测试工程师' }[role || ''] || role || ''
})

const menus = [
  { path: '/dashboard', title: '工作台', icon: Odometer, roles: ['admin', 'manager', 'engineer'] },
  { path: '/projects', title: '项目管理', icon: Folder, roles: ['admin', 'manager', 'engineer'] },
  { path: '/generate', title: 'AI 用例生成', icon: MagicStick, roles: ['admin', 'manager', 'engineer'] },
  { path: '/knowledge', title: '知识库', icon: Collection, roles: ['admin', 'manager', 'engineer'] },
  { path: '/scripts', title: '脚本管理', icon: Document, roles: ['admin', 'manager', 'engineer'] },
  { path: '/script-templates', title: '脚本模板', icon: Files, roles: ['admin', 'manager'] },
  { path: '/statistics', title: '统计报表', icon: TrendCharts, roles: ['admin', 'manager'] },
  { path: '/logs', title: '操作日志', icon: Memo, roles: ['admin', 'manager'] },
  { path: '/settings', title: '系统设置', icon: Setting, roles: ['admin'] },
  { path: '/users', title: '用户管理', icon: User, roles: ['admin'] },
]

const visibleMenus = computed(() =>
  menus.filter((m) => !m.roles || m.roles.includes(userStore.userInfo?.role || '')),
)

const handleCommand = (cmd: string) => {
  if (cmd === 'logout') {
    userStore.logout()
    router.push('/login')
  }
}
</script>

<style scoped>
.layout {
  height: 100%;
}

.aside {
  background: #001529;
}

.logo {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 18px 20px;
  color: #fff;
  font-size: 16px;
  font-weight: 600;
  border-bottom: 1px solid rgba(255, 255, 255, 0.08);
}

.aside :deep(.el-menu) {
  border-right: none;
}

.header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  background: #fff;
  border-bottom: 1px solid #e4e7ed;
}

.header-title {
  font-size: 16px;
  font-weight: 600;
  color: #303133;
}

.user-info {
  display: flex;
  align-items: center;
  gap: 4px;
  cursor: pointer;
  color: #606266;
}

.header-right {
  display: flex;
  align-items: center;
  gap: 20px;
}

.notif-badge {
  cursor: pointer;
}

.notif-icon {
  color: #606266;
}

.notif-panel {
  padding: 4px 0;
}

.notif-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 6px 12px;
  border-bottom: 1px solid #ebeef5;
}

.notif-title {
  font-weight: 600;
  color: #303133;
}

.notif-item {
  padding: 10px 12px;
  cursor: pointer;
  border-bottom: 1px solid #f2f3f5;
}

.notif-item:hover {
  background: #f5f7fa;
}

.notif-item.unread {
  background: #ecf5ff;
}

.notif-item-title {
  font-size: 13px;
  color: #303133;
  font-weight: 500;
}

.notif-item-content {
  font-size: 12px;
  color: #909399;
  margin-top: 4px;
  word-break: break-all;
}

.notif-item-time {
  font-size: 11px;
  color: #c0c4cc;
  margin-top: 4px;
}

.notif-more {
  text-align: center;
  padding: 8px 0 4px;
  font-size: 13px;
  color: #409eff;
  cursor: pointer;
}

.main {
  background: #f5f7fa;
  overflow-y: auto;
}
</style>
