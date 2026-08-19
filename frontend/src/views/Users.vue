<template>
  <div>
    <el-card shadow="never">
      <div class="toolbar">
        <span class="card-title">成员管理</span>
        <span class="card-desc">管理员可添加成员、分配权限、停用或删除成员</span>
        <div class="flex-1"></div>
        <el-input v-model="keyword" placeholder="搜索用户名/姓名" clearable style="width: 200px" @keyup.enter="search" @clear="search">
          <template #prefix><el-icon><Search /></el-icon></template>
        </el-input>
        <el-button type="primary" @click="openCreate">
          <el-icon><Plus /></el-icon>添加成员
        </el-button>
      </div>

      <el-table :data="list" v-loading="loading" border stripe>
        <el-table-column prop="id" label="ID" width="60" />
        <el-table-column prop="username" label="用户名" min-width="110" />
        <el-table-column prop="real_name" label="姓名" min-width="100">
          <template #default="{ row }">{{ row.real_name || '-' }}</template>
        </el-table-column>
        <el-table-column prop="email" label="邮箱" min-width="150">
          <template #default="{ row }">{{ row.email || '-' }}</template>
        </el-table-column>
        <el-table-column label="角色" width="110">
          <template #default="{ row }">
            <el-tag :type="roleTypeMap[row.role]" size="small">{{ roleMap[row.role] }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="权限" min-width="220">
          <template #default="{ row }">
            <template v-if="row.role === 'admin'">
              <el-tag type="danger" size="small">全部权限</el-tag>
            </template>
            <template v-else-if="(row.permissions || []).length">
              <el-tag v-for="code in row.permissions.slice(0, 3)" :key="code" size="small" class="perm-tag">
                {{ permLabel(code) }}
              </el-tag>
              <el-tag v-if="row.permissions.length > 3" type="info" size="small" class="perm-tag">
                +{{ row.permissions.length - 3 }}
              </el-tag>
            </template>
            <span v-else class="no-perm">未分配权限</span>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="90">
          <template #default="{ row }">
            <el-tag :type="row.is_active ? 'success' : 'info'" size="small">{{ row.is_active ? '启用' : '停用' }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="created_at" label="创建时间" width="170" />
        <el-table-column label="操作" width="250" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" @click="openEdit(row)">编辑/权限</el-button>
            <el-button link type="warning" @click="openReset(row)">重置密码</el-button>
            <el-button link :type="row.is_active ? 'danger' : 'success'" @click="toggleStatus(row)">
              {{ row.is_active ? '停用' : '启用' }}
            </el-button>
            <el-button link type="danger" :disabled="row.id === currentUserId" @click="handleDelete(row)">
              删除
            </el-button>
          </template>
        </el-table-column>
      </el-table>
      <el-pagination
        class="pagination"
        v-model:current-page="page"
        :page-size="pageSize"
        :total="total"
        layout="total, prev, pager, next"
        @current-change="loadData"
      />
    </el-card>

    <!-- 添加/编辑成员 -->
    <el-dialog v-model="dialogVisible" :title="editing ? '编辑成员与权限' : '添加成员'" width="640px" top="6vh">
      <el-form ref="formRef" :model="form" :rules="rules" label-width="80px">
        <el-row :gutter="16">
          <el-col :span="12">
            <el-form-item label="用户名" prop="username">
              <el-input v-model="form.username" :disabled="!!editing" placeholder="登录账号" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="密码" prop="password" v-if="!editing">
              <el-input v-model="form.password" type="password" show-password placeholder="至少 6 位" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="姓名" prop="real_name">
              <el-input v-model="form.real_name" placeholder="真实姓名（可选）" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="角色" prop="role">
              <el-select v-model="form.role" style="width: 100%" @change="onRoleChange">
                <el-option label="管理员" value="admin" />
                <el-option label="项目经理" value="manager" />
                <el-option label="测试工程师" value="engineer" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="邮箱" prop="email">
              <el-input v-model="form.email" placeholder="邮箱（可选）" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="手机号" prop="phone">
              <el-input v-model="form.phone" placeholder="手机号（可选）" />
            </el-form-item>
          </el-col>
        </el-row>

        <el-alert
          v-if="!editing && form.role !== 'admin'"
          type="info"
          :closable="false"
          show-icon
          title="成员使用初始密码首次登录时，将强制要求修改密码"
          class="perm-alert"
        />

        <el-divider content-position="left">权限配置</el-divider>
        <el-alert
          v-if="form.role === 'admin'"
          type="info"
          :closable="false"
          show-icon
          title="管理员拥有全部权限，无需单独配置"
          class="perm-alert"
        />
        <div v-else class="perm-groups">
          <div v-for="group in permissionGroups" :key="group.name" class="perm-group">
            <div class="perm-group-title">{{ group.name }}</div>
            <el-checkbox-group v-model="form.permissions">
              <el-checkbox v-for="item in group.items" :key="item.code" :value="item.code" class="perm-check">
                {{ item.label }}
              </el-checkbox>
            </el-checkbox-group>
          </div>
          <div class="perm-actions">
            <el-button size="small" @click="fillDefault">按角色默认</el-button>
            <el-button size="small" @click="selectAll">全选</el-button>
            <el-button size="small" @click="clearAll">清空</el-button>
          </div>
        </div>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="handleSave">保存</el-button>
      </template>
    </el-dialog>

    <!-- 重置密码 -->
    <el-dialog v-model="resetVisible" title="重置密码" width="420px">
      <el-form label-width="80px" @submit.prevent>
        <el-form-item label="新密码">
          <el-input v-model="newPassword" type="password" show-password placeholder="至少 6 位" />
        </el-form-item>
        <el-form-item v-if="resetTarget?.role !== 'admin'">
          <el-alert
            type="warning"
            :closable="false"
            show-icon
            title="重置后，该成员下次登录将强制修改密码"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="resetVisible = false">取消</el-button>
        <el-button type="primary" :loading="resetting" @click="handleReset">确定</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus, Search } from '@element-plus/icons-vue'
import { userApi } from '@/api'
import { PERMISSION_CATALOG, defaultPermissionsFor } from '@/utils/permissions'

const list = ref<any[]>([])
const loading = ref(false)
const page = ref(1)
const pageSize = ref(10)
const total = ref(0)
const keyword = ref('')
const currentUserId = ref<number | undefined>(undefined)

const dialogVisible = ref(false)
const editing = ref<any>(null)
const saving = ref(false)
const formRef = ref<any>(null)
const form = reactive({
  username: '', password: '', real_name: '', email: '', phone: '', role: 'engineer',
  permissions: [] as string[],
})

const resetVisible = ref(false)
const resetTarget = ref<any>(null)
const newPassword = ref('')
const resetting = ref(false)

const roleMap: Record<string, string> = { admin: '管理员', manager: '项目经理', engineer: '测试工程师' }
const roleTypeMap: Record<string, string> = { admin: 'danger', manager: 'warning', engineer: 'primary' }

const permLabelMap = computed(() => Object.fromEntries(PERMISSION_CATALOG.map((p) => [p.code, p.label])))
const permLabel = (code: string) => permLabelMap.value[code] || code

const permissionGroups = computed(() => {
  const groups = new Map<string, typeof PERMISSION_CATALOG>()
  for (const p of PERMISSION_CATALOG) {
    const key = p.group
    if (!groups.has(key)) groups.set(key, [])
    groups.get(key)!.push(p)
  }
  return Array.from(groups.entries()).map(([name, items]) => ({ name, items }))
})

const rules = {
  username: [{ required: true, message: '请输入用户名', trigger: 'blur' }],
  password: [{ required: true, min: 6, message: '密码至少 6 位', trigger: 'blur' }],
  role: [{ required: true, message: '请选择角色', trigger: 'change' }],
}

const search = () => {
  page.value = 1
  loadData()
}

const loadData = async () => {
  loading.value = true
  try {
    const data = await userApi.list({ page: page.value, page_size: pageSize.value, keyword: keyword.value || undefined })
    list.value = data.list
    total.value = data.total
  } finally {
    loading.value = false
  }
}

const openCreate = () => {
  editing.value = null
  Object.assign(form, {
    username: '', password: '', real_name: '', email: '', phone: '', role: 'engineer',
    permissions: defaultPermissionsFor('engineer'),
  })
  dialogVisible.value = true
}

const openEdit = async (row: any) => {
  editing.value = row
  Object.assign(form, {
    username: row.username, password: '', real_name: row.real_name || '', email: row.email || '',
    phone: row.phone || '', role: row.role,
    permissions: row.role === 'admin' ? [] : [...(row.permissions || [])],
  })
  dialogVisible.value = true
}

const onRoleChange = (role: string) => {
  // 角色变更时重置为角色默认权限，便于管理员在此基础上自定义
  if (!editing.value || !form.permissions.length) {
    form.permissions = defaultPermissionsFor(role)
  } else if (role !== editing.value?.role) {
    form.permissions = defaultPermissionsFor(role)
  }
}

const fillDefault = () => {
  form.permissions = defaultPermissionsFor(form.role)
}

const selectAll = () => {
  form.permissions = PERMISSION_CATALOG.map((p) => p.code)
}

const clearAll = () => {
  form.permissions = []
}

const handleSave = async () => {
  const valid = await formRef.value.validate().catch(() => false)
  if (!valid) return
  saving.value = true
  try {
    const payload = {
      real_name: form.real_name, email: form.email, phone: form.phone, role: form.role,
      permissions: form.role === 'admin' ? undefined : form.permissions,
    }
    if (editing.value) {
      await userApi.update(editing.value.id, payload)
      ElMessage.success('成员已更新')
    } else {
      await userApi.create({
        username: form.username, password: form.password, ...payload,
      })
      ElMessage.success('成员已添加')
    }
    dialogVisible.value = false
    loadData()
  } finally {
    saving.value = false
  }
}

const openReset = (row: any) => {
  resetTarget.value = row
  newPassword.value = ''
  resetVisible.value = true
}

const handleReset = async () => {
  if (newPassword.value.length < 6) return ElMessage.warning('新密码至少 6 位')
  resetting.value = true
  try {
    await userApi.resetPassword(resetTarget.value.id, newPassword.value)
    ElMessage.success('密码已重置')
    resetVisible.value = false
  } finally {
    resetting.value = false
  }
}

const toggleStatus = async (row: any) => {
  const action = row.is_active ? '停用' : '启用'
  await ElMessageBox.confirm(`确认${action}成员「${row.username}」？`, '提示', { type: 'warning' })
  await userApi.setStatus(row.id, !row.is_active)
  ElMessage.success(`已${action}`)
  loadData()
}

const handleDelete = async (row: any) => {
  await ElMessageBox.confirm(
    `确定删除成员「${row.username}」吗？其名下数据将保留但创建人信息会被清除，该操作不可恢复。`,
    '删除确认',
    { type: 'warning' },
  )
  await userApi.remove(row.id)
  ElMessage.success('成员已删除')
  loadData()
}

onMounted(() => {
  try {
    const info = JSON.parse(localStorage.getItem('user_info') || 'null')
    currentUserId.value = info?.id
  } catch {
    currentUserId.value = undefined
  }
  loadData()
})
</script>

<style scoped>
.toolbar {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 16px;
}

.card-title {
  font-weight: 600;
}

.card-desc {
  color: #909399;
  font-size: 12px;
}

.flex-1 {
  flex: 1;
}

.pagination {
  margin-top: 16px;
  justify-content: flex-end;
}

.perm-tag {
  margin-right: 4px;
}

.no-perm {
  color: #c0c4cc;
  font-size: 12px;
}

.perm-alert {
  margin-bottom: 8px;
}

.perm-groups {
  max-height: 280px;
  overflow-y: auto;
  padding: 4px;
}

.perm-group {
  margin-bottom: 12px;
}

.perm-group-title {
  font-size: 13px;
  font-weight: 600;
  color: #606266;
  margin-bottom: 8px;
}

.perm-check {
  width: 33%;
  margin-right: 0;
  margin-bottom: 6px;
}

.perm-actions {
  margin-top: 4px;
  padding-top: 8px;
  border-top: 1px dashed #e4e7ed;
}
</style>
