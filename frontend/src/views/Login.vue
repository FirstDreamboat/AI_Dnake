<template>
  <div class="login-container">
    <div class="login-card">
      <div class="login-header">
        <h1>AI 驱动的研发质量前置平台</h1>
        <p>狄耐克 · 从需求体检到测试用例自动生成</p>
      </div>
      <el-form ref="formRef" :model="form" :rules="rules" size="large" @keyup.enter="handleLogin">
        <el-form-item prop="username">
          <el-input v-model="form.username" placeholder="用户名" :prefix-icon="User" clearable />
        </el-form-item>
        <el-form-item prop="password">
          <el-input v-model="form.password" type="password" placeholder="密码" :prefix-icon="Lock" show-password />
        </el-form-item>
        <el-form-item prop="captchaCode">
          <div class="captcha-row">
            <el-input v-model="form.captchaCode" placeholder="验证码" :prefix-icon="Key" clearable maxlength="4" />
            <img v-if="captchaImg" :src="captchaImg" class="captcha-img" alt="验证码" title="看不清？点击刷新" @click="loadCaptcha" />
          </div>
        </el-form-item>
        <el-form-item>
          <el-button type="primary" class="login-btn" :loading="loading" @click="handleLogin">
            登 录
          </el-button>
        </el-form-item>
      </el-form>
    </div>
  </div>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, type FormInstance, type FormRules } from 'element-plus'
import { User, Lock, Key } from '@element-plus/icons-vue'
import { useUserStore } from '@/stores/user'
import { authApi } from '@/api'

const router = useRouter()
const userStore = useUserStore()

const formRef = ref<FormInstance>()
const loading = ref(false)
const captchaId = ref('')
const captchaImg = ref('')
const form = reactive({ username: '', password: '', captchaCode: '' })

const rules: FormRules = {
  username: [{ required: true, message: '请输入用户名', trigger: 'blur' }],
  password: [{ required: true, message: '请输入密码', trigger: 'blur' }],
  captchaCode: [{ required: true, message: '请输入验证码', trigger: 'blur' }],
}

const loadCaptcha = async () => {
  try {
    const data = await authApi.captcha()
    captchaId.value = data.captcha_id
    captchaImg.value = data.image
    form.captchaCode = ''
  } catch {
    // 错误提示由请求拦截器统一处理
  }
}

const handleLogin = async () => {
  const valid = await formRef.value?.validate().catch(() => false)
  if (!valid) return
  loading.value = true
  try {
    await userStore.login(form.username, form.password, captchaId.value, form.captchaCode)
    ElMessage.success('登录成功')
    router.push('/')
  } catch {
    // 登录失败（如验证码错误）刷新验证码
    loadCaptcha()
  } finally {
    loading.value = false
  }
}

onMounted(loadCaptcha)
</script>

<style scoped>
.login-container {
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  background: linear-gradient(135deg, #1a2a6c 0%, #2d5aa0 50%, #1e88e5 100%);
}

.login-card {
  width: 400px;
  padding: 40px;
  background: #fff;
  border-radius: 12px;
  box-shadow: 0 8px 30px rgba(0, 0, 0, 0.2);
}

.login-header {
  text-align: center;
  margin-bottom: 32px;
}

.login-header h1 {
  font-size: 22px;
  color: #1a2a6c;
}

.login-header p {
  margin-top: 8px;
  color: #909399;
  font-size: 13px;
}

.login-btn {
  width: 100%;
}

.captcha-row {
  display: flex;
  gap: 10px;
  width: 100%;
}

.captcha-row .el-input {
  flex: 1;
}

.captcha-img {
  width: 120px;
  height: 40px;
  border-radius: 6px;
  border: 1px solid #dcdfe6;
  cursor: pointer;
  flex-shrink: 0;
}
</style>
