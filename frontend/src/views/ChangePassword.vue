<template>
  <div class="cp-container">
    <div class="cp-card">
      <div class="cp-header">
        <h2>修改初始密码</h2>
        <p>首次登录或密码被重置后，需要修改密码才能继续使用</p>
      </div>
      <el-form ref="formRef" :model="form" :rules="rules" size="large" @keyup.enter="handleSubmit">
        <el-form-item prop="old_password">
          <el-input v-model="form.old_password" type="password" placeholder="原密码" :prefix-icon="Lock" show-password />
        </el-form-item>
        <el-form-item prop="new_password">
          <el-input v-model="form.new_password" type="password" placeholder="新密码（6-64位）" :prefix-icon="Key" show-password />
        </el-form-item>
        <el-form-item prop="confirm_password">
          <el-input v-model="form.confirm_password" type="password" placeholder="确认新密码" :prefix-icon="Key" show-password />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" class="cp-btn" :loading="loading" @click="handleSubmit">
            确认修改
          </el-button>
        </el-form-item>
      </el-form>
      <div class="cp-footer">
        <el-link type="primary" :underline="false" @click="handleLogout">退出登录</el-link>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, type FormInstance, type FormRules } from 'element-plus'
import { Lock, Key } from '@element-plus/icons-vue'
import { authApi } from '@/api'
import { useUserStore } from '@/stores/user'

const router = useRouter()
const userStore = useUserStore()

const formRef = ref<FormInstance>()
const loading = ref(false)
const form = reactive({ old_password: '', new_password: '', confirm_password: '' })

const validateConfirm = (_rule: unknown, value: string, callback: (err?: Error) => void) => {
  if (value !== form.new_password) {
    callback(new Error('两次输入的密码不一致'))
  } else {
    callback()
  }
}

const rules: FormRules = {
  old_password: [{ required: true, message: '请输入原密码', trigger: 'blur' }],
  new_password: [
    { required: true, message: '请输入新密码', trigger: 'blur' },
    { min: 6, max: 64, message: '密码长度为 6-64 位', trigger: 'blur' },
  ],
  confirm_password: [
    { required: true, message: '请再次输入新密码', trigger: 'blur' },
    { validator: validateConfirm, trigger: 'blur' },
  ],
}

const handleSubmit = async () => {
  const valid = await formRef.value?.validate().catch(() => false)
  if (!valid) return
  loading.value = true
  try {
    await authApi.changePassword({ old_password: form.old_password, new_password: form.new_password })
    userStore.clearMustChangePassword()
    ElMessage.success('密码修改成功')
    router.push('/')
  } catch {
    // 错误提示由请求拦截器统一处理
  } finally {
    loading.value = false
  }
}

const handleLogout = () => {
  userStore.logout()
  router.push('/login')
}
</script>

<style scoped>
.cp-container {
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  background: linear-gradient(135deg, #1a2a6c 0%, #2d5aa0 50%, #1e88e5 100%);
}

.cp-card {
  width: 420px;
  padding: 40px;
  background: #fff;
  border-radius: 12px;
  box-shadow: 0 8px 30px rgba(0, 0, 0, 0.2);
}

.cp-header {
  text-align: center;
  margin-bottom: 28px;
}

.cp-header h2 {
  font-size: 20px;
  color: #1a2a6c;
}

.cp-header p {
  margin-top: 8px;
  color: #909399;
  font-size: 13px;
}

.cp-btn {
  width: 100%;
}

.cp-footer {
  margin-top: 8px;
  text-align: center;
}
</style>
