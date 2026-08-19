// 权限点目录（code 必须与后端 app/core/permissions.py 保持一致）
export interface PermissionItem {
  code: string
  label: string
  group: string
  description?: string
}

export const PERMISSION_CATALOG: PermissionItem[] = [
  { code: 'project', label: '项目管理', group: '业务功能', description: '查看与管理测试项目' },
  { code: 'generate', label: 'AI 用例生成', group: '业务功能', description: '使用 AI 生成与评审测试用例' },
  { code: 'knowledge', label: '知识库', group: '业务功能', description: '上传与管理知识库文档' },
  { code: 'script', label: '脚本管理', group: '业务功能', description: '管理与下载测试脚本' },
  { code: 'script_template', label: '脚本模板', group: '管理功能', description: '创建/编辑/删除自定义脚本模板' },
  { code: 'statistics', label: '统计报表', group: '管理功能', description: '查看统计报表与趋势分析' },
  { code: 'logs', label: '操作日志', group: '管理功能', description: '查看与检索操作日志' },
  { code: 'settings', label: '系统设置', group: '管理功能', description: '查看与修改系统配置' },
  { code: 'user_manage', label: '成员管理', group: '管理功能', description: '添加成员、分配权限、停用与删除成员' },
]

export const ALL_PERMISSIONS = PERMISSION_CATALOG.map((p) => p.code)

// 各角色默认权限（admin 拥有全部权限）
export const DEFAULT_PERMISSIONS: Record<string, string[]> = {
  manager: ['project', 'generate', 'knowledge', 'script', 'script_template', 'statistics', 'logs'],
  engineer: ['project', 'generate', 'knowledge', 'script'],
}

export function defaultPermissionsFor(role: string): string[] {
  if (role === 'admin') return [...ALL_PERMISSIONS]
  return [...(DEFAULT_PERMISSIONS[role] || [])]
}
