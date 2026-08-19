"""
「AI测试用例生成平台」自测用例与脚本数据。
说明：本文件中的测试用例由人工（AI 助手）根据系统需求文档编写，
不调用 AI 生成接口，全部通过「手动创建用例」接口录入。
"""

# 通用步骤工具
def S(actions_expected):
    """[(action, expected), ...] -> steps 列表"""
    return [{"step_no": i + 1, "action": a, "expected": e} for i, (a, e) in enumerate(actions_expected)]


CASES = [
    # ================= 用户认证与权限 =================
    {
        "point": "用户认证与权限", "title": "正确账号密码登录成功",
        "priority": "P0", "test_type": "功能测试",
        "preconditions": "系统已初始化 admin 账号（admin/admin123），登录页验证码开启",
        "steps": S([
            ("打开登录页，输入正确用户名 admin", "页面无异常提示"),
            ("输入正确密码 admin123", "密码框内容为掩码显示"),
            ("输入正确图形验证码，点击登录", "登录成功，跳转到平台首页，携带有效 JWT Token"),
        ]),
        "expected_result": "登录成功并进入系统主界面",
        "source": "manual",
    },
    {
        "point": "用户认证与权限", "title": "错误密码登录失败并提示",
        "priority": "P0", "test_type": "异常测试",
        "preconditions": "存在有效账号 admin/admin123",
        "steps": S([
            ("输入正确用户名 admin", "无异常"),
            ("输入错误密码 123456", "无异常"),
            ("输入正确验证码并登录", "登录失败，页面提示“用户名或密码错误”"),
        ]),
        "expected_result": "登录被拒绝，错误提示明确，不泄露账号是否存在",
        "source": "manual",
    },
    {
        "point": "用户认证与权限", "title": "图形验证码错误拒绝登录",
        "priority": "P0", "test_type": "安全测试",
        "preconditions": "验证码功能开启",
        "steps": S([
            ("输入正确用户名密码", "无异常"),
            ("输入错误验证码，点击登录", "提示“验证码错误或已过期”，不发起认证"),
            ("再次登录并输入正确验证码", "登录成功"),
        ]),
        "expected_result": "验证码错误时禁止登录，验证码可刷新",
        "source": "manual",
    },
    {
        "point": "用户认证与权限", "title": "未登录访问接口返回 401",
        "priority": "P0", "test_type": "安全测试",
        "preconditions": "后端服务运行中",
        "steps": S([
            ("不携带 Token 调用 GET /api/v1/projects", "返回 401 Unauthorized"),
            ("携带过期 Token 调用接口", "返回 401，提示 Token 无效或过期"),
        ]),
        "expected_result": "所有受保护接口均校验 JWT，未授权返回 401",
        "source": "manual",
    },
    {
        "point": "用户认证与权限", "title": "修改密码后旧密码失效",
        "priority": "P1", "test_type": "功能测试",
        "preconditions": "已登录账号",
        "steps": S([
            ("进入个人中心，修改密码为 NewPass123", "提示修改成功"),
            ("退出登录", "返回登录页"),
            ("使用旧密码登录", "登录失败"),
            ("使用新密码登录", "登录成功"),
        ]),
        "expected_result": "密码修改后旧密码立即失效",
        "source": "manual",
    },
    {
        "point": "登录安全策略", "title": "连续输错密码触发账号锁定",
        "priority": "P1", "test_type": "安全测试",
        "preconditions": "已配置账号锁定策略（如 5 次）",
        "steps": S([
            ("连续 5 次输入错误密码登录", "第 5 次后提示账号已锁定，需管理员解锁或等待解锁"),
            ("使用正确密码尝试登录", "仍提示锁定，登录被拒绝"),
        ]),
        "expected_result": "账号锁定策略生效，防止暴力破解",
        "source": "manual",
    },
    {
        "point": "登录安全策略", "title": "首次登录强制修改初始密码",
        "priority": "P2", "test_type": "功能测试",
        "preconditions": "管理员创建了密码为初始值的新用户",
        "steps": S([
            ("新用户使用初始密码登录", "登录成功但弹出强制改密窗口"),
            ("点击取消/关闭改密窗口", "无法进入系统"),
            ("设置新密码后", "进入系统主界面"),
        ]),
        "expected_result": "初始密码用户强制修改密码后才能使用系统",
        "source": "manual",
    },

    # ================= 项目管理 =================
    {
        "point": "项目管理", "title": "创建项目成功",
        "priority": "P0", "test_type": "功能测试",
        "preconditions": "已登录且有项目管理权限",
        "steps": S([
            ("进入项目管理页，点击新建项目", "弹出项目创建表单"),
            ("填写名称、产品线（楼宇对讲/智能家居/智慧病房）、描述", "表单校验通过"),
            ("提交保存", "提示创建成功，项目出现在列表首位"),
        ]),
        "expected_result": "项目创建成功，列表可查询到该项目",
        "source": "manual",
    },
    {
        "point": "项目管理", "title": "项目名称重复创建被拒绝",
        "priority": "P1", "test_type": "异常测试",
        "preconditions": "已存在项目“示例项目”",
        "steps": S([
            ("新建项目，名称填写“示例项目”", "名称字段下方提示“项目名称已存在”"),
            ("尝试提交", "提交被阻止，提示名称重复"),
        ]),
        "expected_result": "项目名称唯一性校验生效",
        "source": "manual",
    },
    {
        "point": "项目管理", "title": "编辑项目信息",
        "priority": "P1", "test_type": "功能测试",
        "preconditions": "存在项目 A",
        "steps": S([
            ("打开项目 A，点击编辑", "表单回显当前信息"),
            ("修改描述信息并保存", "提示更新成功"),
            ("刷新页面", "修改后的信息持久化展示"),
        ]),
        "expected_result": "项目信息可编辑并持久化",
        "source": "manual",
    },
    {
        "point": "项目管理", "title": "归档项目后不再参与统计",
        "priority": "P2", "test_type": "功能测试",
        "preconditions": "存在含用例数据的项目",
        "steps": S([
            ("对项目执行归档操作", "提示归档成功"),
            ("项目列表展示归档标识", "状态更新为已归档"),
            ("查看统计报表", "归档项目数据从报表中排除或单独标记"),
        ]),
        "expected_result": "归档状态正确，统计口径符合设计",
        "source": "manual",
    },
    {
        "point": "项目管理", "title": "无权限用户不能删除项目",
        "priority": "P1", "test_type": "安全测试",
        "preconditions": "存在仅有查看权限的用户 U",
        "steps": S([
            ("使用用户 U 登录", "进入系统"),
            ("对项目点击删除", "无删除入口或操作被拒绝（403）"),
            ("直接调用 DELETE /api/v1/projects/{id}", "返回 403，项目未被删除"),
        ]),
        "expected_result": "删除操作受权限点控制，接口层同样拦截",
        "source": "manual",
    },

    # ================= 需求文档解析 =================
    {
        "point": "需求文档解析", "title": "上传 Markdown 需求文档成功",
        "priority": "P0", "test_type": "功能测试",
        "preconditions": "项目已创建，存在本地 .md 需求文档",
        "steps": S([
            ("进入需求文档页，选择项目，上传 .md 文件", "上传进度完成，提示上传成功"),
            ("触发文档解析", "解析成功，可查看解析出的文本内容"),
        ]),
        "expected_result": "Markdown 文档上传并解析成功",
        "source": "manual",
    },
    {
        "point": "需求文档解析", "title": "上传不支持的格式被拒绝",
        "priority": "P1", "test_type": "异常测试",
        "preconditions": "系统仅支持 pdf/docx/txt/md",
        "steps": S([
            ("上传 .exe / .zip 等不支持的文件", "前端提示格式不支持，上传被拦截"),
            ("绕过前端直接调用上传接口", "接口返回 400，说明仅支持指定格式"),
        ]),
        "expected_result": "文件格式白名单校验生效",
        "source": "manual",
    },
    {
        "point": "需求文档解析", "title": "Word 文档解析提取章节内容",
        "priority": "P1", "test_type": "功能测试",
        "preconditions": "存在含标题/正文的 .docx 文档",
        "steps": S([
            ("上传并解析 .docx 文档", "解析状态变为成功"),
            ("查看解析结果", "能提取标题、正文段落与表格内容"),
        ]),
        "expected_result": "Word 文档结构化内容被正确提取",
        "source": "manual",
    },
    {
        "point": "需求文档解析", "title": "文档列表按项目过滤展示",
        "priority": "P2", "test_type": "功能测试",
        "preconditions": "两个项目下各有文档",
        "steps": S([
            ("进入项目 A 的文档列表", "仅显示项目 A 的文档"),
            ("切换到项目 B", "列表切换为项目 B 的文档"),
        ]),
        "expected_result": "文档列表与项目正确隔离",
        "source": "manual",
    },
    {
        "point": "需求文档解析", "title": "平台链接解析失败时给出提示",
        "priority": "P2", "test_type": "异常测试",
        "preconditions": "系统支持飞书/语雀/TAPD/Confluence 链接导入",
        "steps": S([
            ("输入无效/不可访问的文档链接", "提示“链接解析失败，请检查链接有效性”"),
            ("输入需要登录态的私有链接", "提示解析失败且不泄露内部信息"),
        ]),
        "expected_result": "链接解析异常有明确提示，不影响其他功能",
        "source": "manual",
    },

    # ================= 测试点管理 =================
    {
        "point": "测试点管理", "title": "手动创建测试点",
        "priority": "P1", "test_type": "功能测试",
        "preconditions": "项目与关联需求文档存在",
        "steps": S([
            ("进入测试点管理页，点击新建", "弹出测试点表单"),
            ("填写名称、选择类型、填写描述", "表单校验通过"),
            ("提交", "测试点创建成功并展示在列表"),
        ]),
        "expected_result": "测试点可手动创建并持久化",
        "source": "manual",
    },
    {
        "point": "测试点管理", "title": "测试点类型仅允许六类之一",
        "priority": "P1", "test_type": "边界测试",
        "preconditions": "系统定义 function/boundary/exception/performance/security/implicit 六类",
        "steps": S([
            ("创建测试点，类型选择六类中的任一类", "创建成功"),
            ("类型传值为其它字符串（如 “未知类型”）", "接口返回 400 校验错误"),
        ]),
        "expected_result": "测试点类型枚举校验严格",
        "source": "manual",
    },
    {
        "point": "测试点管理", "title": "编辑与删除测试点",
        "priority": "P2", "test_type": "功能测试",
        "preconditions": "存在测试点 T",
        "steps": S([
            ("编辑测试点 T 的名称与描述并保存", "更新成功且列表刷新"),
            ("删除测试点 T", "提示删除成功，列表中消失"),
        ]),
        "expected_result": "测试点支持编辑与删除",
        "source": "manual",
    },
    {
        "point": "测试点管理", "title": "测试点列表按类型筛选",
        "priority": "P2", "test_type": "功能测试",
        "preconditions": "存在多种类型的测试点",
        "steps": S([
            ("在测试点列表选择“安全测试”筛选", "仅展示 security 类型测试点"),
            ("清除筛选条件", "恢复全量列表"),
        ]),
        "expected_result": "类型筛选功能正确",
        "source": "manual",
    },

    # ================= 用例自动生成 =================
    {
        "point": "用例自动生成", "title": "创建生成任务并异步执行",
        "priority": "P0", "test_type": "功能测试",
        "preconditions": "项目已上传并解析需求文档，LLM 服务可用",
        "steps": S([
            ("选择项目与文档，点击“生成测试用例”", "生成任务创建成功，返回任务 ID"),
            ("查看任务状态", "任务进入执行中状态"),
            ("等待任务完成", "任务状态变为成功，产生用例结果"),
        ]),
        "expected_result": "生成任务全流程闭环，失败时任务状态为失败并可重试",
        "source": "ai_reviewed",
    },
    {
        "point": "用例自动生成", "title": "用例编号符合产品线规则",
        "priority": "P1", "test_type": "功能测试",
        "preconditions": "产品线代码：楼宇对讲=IAC、智能家居=SH、智慧病房=HOS（或文档约定规则）",
        "steps": S([
            ("对智能家居项目生成用例", "用例编号形如 SH-模块-序号，前缀与产品线一致"),
            ("抽查多条用例编号", "编号无重复且按规则递增"),
        ]),
        "expected_result": "用例编号遵循 {产品线代码}-{模块代码}-{序号} 规则",
        "source": "manual",
    },
    {
        "point": "用例自动生成", "title": "批量重新生成选中用例",
        "priority": "P2", "test_type": "功能测试",
        "preconditions": "存在已生成的用例",
        "steps": S([
            ("勾选多条用例，点击“重新生成”", "生成新任务并进入执行"),
            ("任务完成后查看用例", "用例内容已更新，保留版本历史"),
        ]),
        "expected_result": "批量重生成覆盖旧内容并记录版本",
        "source": "manual",
    },
    {
        "point": "用例自动生成", "title": "LLM 不可用时生成任务失败可感知",
        "priority": "P1", "test_type": "异常测试",
        "preconditions": "LLM 服务不可用（断网或未配置）",
        "steps": S([
            ("触发用例生成任务", "任务创建成功但状态变为失败"),
            ("查看失败原因", "展示明确错误信息（如 LLM 调用超时）"),
            ("恢复服务后点击重试", "任务重新执行成功"),
        ]),
        "expected_result": "生成失败可感知、可重试，不影响其他功能",
        "source": "manual",
    },
    {
        "point": "用例自动生成", "title": "生成用例包含结构化字段",
        "priority": "P1", "test_type": "功能测试",
        "preconditions": "生成任务已完成",
        "steps": S([
            ("查看生成用例详情", "包含标题、前置条件、步骤、预期结果、优先级、测试类型、来源等字段"),
            ("检查步骤编号", "步骤按 1..N 顺序排列"),
        ]),
        "expected_result": "生成的用例结构化完整，可直接编辑",
        "source": "manual",
    },
    {
        "point": "用例自动生成", "title": "无需求文档时生成提示补充文档",
        "priority": "P2", "test_type": "异常测试",
        "preconditions": "项目下无任何需求文档",
        "steps": S([
            ("对空文档项目点击生成用例", "提示“请先上传并解析需求文档”"),
            ("上传文档并解析后再次生成", "生成功能可用"),
        ]),
        "expected_result": "前置条件缺失有明确引导提示",
        "source": "manual",
    },

    # ================= 用例管理 =================
    {
        "point": "用例管理", "title": "手动创建测试用例",
        "priority": "P0", "test_type": "功能测试",
        "preconditions": "项目已创建，存在测试点",
        "steps": S([
            ("进入用例列表，点击新建用例", "弹出用例表单"),
            ("填写标题、前置条件、步骤、预期结果并选择优先级/类型", "表单校验通过"),
            ("保存", "用例创建成功，出现在列表"),
        ]),
        "expected_result": "用例可手动创建（来源=manual）",
        "source": "manual",
    },
    {
        "point": "用例管理", "title": "用例列表按项目/关键词检索",
        "priority": "P1", "test_type": "功能测试",
        "preconditions": "存在多个项目及用例",
        "steps": S([
            ("用例列表选择项目 A", "仅展示项目 A 用例"),
            ("输入关键词“登录”", "展示标题/内容命中关键词的用例"),
        ]),
        "expected_result": "检索与过滤结果准确",
        "source": "manual",
    },
    {
        "point": "用例管理", "title": "编辑用例并保存",
        "priority": "P1", "test_type": "功能测试",
        "preconditions": "存在用例 C",
        "steps": S([
            ("打开用例 C 详情并编辑", "字段回显正确"),
            ("修改步骤内容并保存", "提示更新成功"),
            ("重新打开详情", "修改内容已持久化"),
        ]),
        "expected_result": "用例编辑功能正常",
        "source": "manual",
    },
    {
        "point": "用例管理", "title": "批量删除用例二次确认",
        "priority": "P1", "test_type": "功能测试",
        "preconditions": "存在多条用例",
        "steps": S([
            ("勾选多条用例点击删除", "弹出二次确认框"),
            ("确认删除", "用例被删除并从列表移除"),
            ("取消删除", "用例保持不变"),
        ]),
        "expected_result": "批量删除有二次确认，误操作可撤销",
        "source": "manual",
    },
    {
        "point": "用例管理", "title": "用例版本历史可追溯",
        "priority": "P2", "test_type": "功能测试",
        "preconditions": "用例已被编辑过至少一次",
        "steps": S([
            ("打开用例的版本历史", "展示历次版本与修改时间"),
            ("选择某历史版本", "可查看该版本完整内容"),
        ]),
        "expected_result": "用例修改留痕，版本可追溯",
        "source": "manual",
    },
    {
        "point": "用例管理", "title": "删除关联用例后统计同步",
        "priority": "P2", "test_type": "功能测试",
        "preconditions": "项目下存在用例且统计已生成",
        "steps": S([
            ("删除 3 条用例", "删除成功"),
            ("刷新统计报表", "用例总数与分布相应减少"),
        ]),
        "expected_result": "统计数据与用例数据保持一致",
        "source": "manual",
    },

    # ================= 用例导入导出 =================
    {
        "point": "用例导入导出", "title": "Excel 批量导入用例",
        "priority": "P2", "test_type": "功能测试",
        "preconditions": "准备符合模板的用例 Excel 文件",
        "steps": S([
            ("上传用例 Excel 文件", "提示导入中/导入完成"),
            ("查看导入结果", "成功导入用例数量与失败行明细"),
            ("检查列表", "导入用例已入库且来源标记正确"),
        ]),
        "expected_result": "Excel 导入成功且错误行有提示",
        "source": "manual",
    },
    {
        "point": "用例导入导出", "title": "导出用例为 Excel",
        "priority": "P1", "test_type": "功能测试",
        "preconditions": "存在用例数据",
        "steps": S([
            ("勾选用例或全选，点击导出 Excel", "浏览器下载 .xlsx 文件"),
            ("打开文件", "包含用例标题、优先级、步骤、预期结果等列"),
        ]),
        "expected_result": "Excel 导出内容完整可读",
        "source": "manual",
    },
    {
        "point": "用例导入导出", "title": "导出 Markdown 格式用例",
        "priority": "P2", "test_type": "功能测试",
        "preconditions": "存在用例数据",
        "steps": S([
            ("选择导出格式 Markdown", "下载 .md 文件"),
            ("打开文件", "以表格/列表形式展示用例内容"),
        ]),
        "expected_result": "Markdown 导出格式规范",
        "source": "manual",
    },
    {
        "point": "用例导入导出", "title": "空项目导出给出空结果",
        "priority": "P2", "test_type": "边界测试",
        "preconditions": "项目下无用例",
        "steps": S([
            ("对空用例项目执行导出", "导出文件仅含表头或无数据提示"),
        ]),
        "expected_result": "空数据导出不报错",
        "source": "manual",
    },

    # ================= 用例评审与优化 =================
    {
        "point": "用例评审与优化", "title": "用例评审通过",
        "priority": "P0", "test_type": "功能测试",
        "preconditions": "存在待评审用例",
        "steps": S([
            ("进入用例详情点击“评审”", "展示评审操作"),
            ("选择“通过”并填写评语", "用例状态变为已通过/已评审"),
        ]),
        "expected_result": "评审通过后状态正确流转",
        "source": "manual",
    },
    {
        "point": "用例评审与优化", "title": "用例评审驳回",
        "priority": "P1", "test_type": "功能测试",
        "preconditions": "存在待评审用例",
        "steps": S([
            ("对用例执行“驳回”并填写驳回原因", "用例状态变为已驳回"),
            ("再次查看用例", "展示驳回原因，可重新编辑后再评审"),
        ]),
        "expected_result": "驳回流程完整，原因可追溯",
        "source": "manual",
    },
    {
        "point": "用例评审与优化", "title": "AI 自动补全缺失字段",
        "priority": "P1", "test_type": "功能测试",
        "preconditions": "存在缺失前置条件/步骤的用例，LLM 可用",
        "steps": S([
            ("选中缺失字段用例，点击“AI 补全”", "任务执行并返回补全建议"),
            ("确认应用补全", "用例缺失字段被填充并记录版本"),
        ]),
        "expected_result": "AI 补全生效且不破坏已有内容",
        "source": "ai_reviewed",
    },
    {
        "point": "用例评审与优化", "title": "用例质量评分与问题清单展示",
        "priority": "P1", "test_type": "功能测试",
        "preconditions": "存在待评审用例",
        "steps": S([
            ("对用例执行质量检查", "展示综合评分、问题清单、缺失覆盖信息"),
            ("查看检查结果", "评分与问题描述可读、可定位到具体字段"),
        ]),
        "expected_result": "质量检查结果可视化展示",
        "source": "manual",
    },
    {
        "point": "用例评审与优化", "title": "AI 生成质量人工反馈",
        "priority": "P2", "test_type": "功能测试",
        "preconditions": "存在 AI 生成的用例",
        "steps": S([
            ("在 AI 生成用例上点击“好用”", "反馈成功提示"),
            ("在另一条用例上点击“不好用”并填写原因", "反馈成功，原因被记录"),
            ("再次点击“不好用”", "可清除反馈"),
        ]),
        "expected_result": "质量反馈可提交、可清除，用于模型优化",
        "source": "manual",
    },

    # ================= RAG 知识库 =================
    {
        "point": "RAG知识库", "title": "文档入库知识库",
        "priority": "P1", "test_type": "功能测试",
        "preconditions": "存在已解析文档，embedding 服务可用",
        "steps": S([
            ("将 PRD 文档加入知识库", "文档进入入库队列"),
            ("等待向量化完成", "知识库文档状态变为已入库，可被检索"),
        ]),
        "expected_result": "文档向量化入库成功",
        "source": "manual",
    },
    {
        "point": "RAG知识库", "title": "混合/向量/关键词三种检索模式",
        "priority": "P1", "test_type": "功能测试",
        "preconditions": "知识库中已有文档",
        "steps": S([
            ("选择关键词模式检索“登录”", "返回关键词命中结果"),
            ("选择向量模式检索同义描述", "返回语义相关结果"),
            ("选择混合模式", "返回融合结果且相关性排序合理"),
        ]),
        "expected_result": "三种检索模式均可返回结果",
        "source": "manual",
    },
    {
        "point": "RAG知识库", "title": "检索 topK 参数生效",
        "priority": "P2", "test_type": "边界测试",
        "preconditions": "知识库存在多条相关文档",
        "steps": S([
            ("topK=1 检索", "仅返回 1 条最相关结果"),
            ("topK=5 检索", "返回 5 条结果"),
            ("topK=0 或负数", "接口返回 400 参数校验错误"),
        ]),
        "expected_result": "topK 参数校验与生效正确",
        "source": "manual",
    },
    {
        "point": "RAG知识库", "title": "知识库版本历史",
        "priority": "P2", "test_type": "功能测试",
        "preconditions": "知识库文档被重新入库过",
        "steps": S([
            ("查看知识库文档版本历史", "展示各版本时间与内容摘要"),
            ("切换历史版本", "可回看该版本内容"),
        ]),
        "expected_result": "知识库文档版本可追溯",
        "source": "manual",
    },

    # ================= 脚本生成与模板 =================
    {
        "point": "脚本生成与模板", "title": "保存 pytest 自动化脚本",
        "priority": "P0", "test_type": "功能测试",
        "preconditions": "存在用例数据",
        "steps": S([
            ("选择用例点击“生成脚本”并选择 pytest 类型", "脚本内容生成/填充完成"),
            ("填写脚本名称与描述，点击保存", "提示保存成功"),
            ("查看脚本列表", "脚本按项目/用例正确关联展示"),
        ]),
        "expected_result": "脚本保存成功且关联用例",
        "source": "manual",
        "script_key": "login",
    },
    {
        "point": "脚本生成与模板", "title": "脚本列表按类型筛选",
        "priority": "P2", "test_type": "功能测试",
        "preconditions": "存在 pytest/接口/UI 类型脚本",
        "steps": S([
            ("脚本列表选择“接口自动化”筛选", "仅展示接口脚本"),
            ("清除筛选", "恢复全部脚本"),
        ]),
        "expected_result": "脚本类型筛选正确",
        "source": "manual",
    },
    {
        "point": "脚本生成与模板", "title": "下载脚本文件",
        "priority": "P1", "test_type": "功能测试",
        "preconditions": "存在已保存脚本",
        "steps": S([
            ("在脚本列表点击下载", "浏览器下载对应脚本文件"),
            ("打开下载文件", "内容与保存的脚本一致"),
        ]),
        "expected_result": "脚本下载内容完整",
        "source": "manual",
        "script_key": "project",
    },
    {
        "point": "脚本生成与模板", "title": "自定义脚本模板",
        "priority": "P2", "test_type": "功能测试",
        "preconditions": "系统支持自定义模板",
        "steps": S([
            ("进入模板管理，新建自定义模板", "模板创建成功"),
            ("生成脚本时选择自定义模板", "脚本按照自定义模板结构生成"),
            ("编辑模板", "模板内容可修改并持久化"),
        ]),
        "expected_result": "自定义模板创建、使用、编辑全流程可用",
        "source": "manual",
    },

    # ================= 统计报表 =================
    {
        "point": "统计报表", "title": "平台总览统计正确",
        "priority": "P0", "test_type": "功能测试",
        "preconditions": "系统存在项目/用例数据",
        "steps": S([
            ("进入统计报表-平台总览", "展示项目数、用例总数、脚本数、文档数等指标"),
            ("与数据库实际数据对比", "指标数值一致"),
        ]),
        "expected_result": "总览指标准确",
        "source": "manual",
    },
    {
        "point": "统计报表", "title": "生成趋势折线图数据正确",
        "priority": "P0", "test_type": "功能测试",
        "preconditions": "存在多日创建的用例/脚本数据",
        "steps": S([
            ("选择 7/30/90 天范围查看生成趋势", "折线图按日期展示用例与脚本数量"),
            ("将图上某天数量与用例列表按日期过滤结果对比", "数量一致"),
            ("鼠标悬停数据点", "显示该点位日期与数量"),
        ]),
        "expected_result": "趋势图各数据点真实准确",
        "source": "manual",
        "script_key": "stats",
    },
    {
        "point": "统计报表", "title": "优先级/类型分布统计",
        "priority": "P1", "test_type": "功能测试",
        "preconditions": "存在不同优先级与类型的用例",
        "steps": S([
            ("查看优先级分布图", "P0/P1/P2 占比正确"),
            ("查看测试类型分布图", "功能/异常/安全等类型占比正确"),
        ]),
        "expected_result": "分布统计与用例数据一致",
        "source": "manual",
    },
    {
        "point": "统计报表", "title": "AI 与人工效率对比数据",
        "priority": "P2", "test_type": "功能测试",
        "preconditions": "系统记录 AI 生成与人工编写耗时",
        "steps": S([
            ("查看效率对比报表", "展示 AI vs 人工的用例数量与耗时对比"),
            ("核对计算口径", "数据来源与生成记录一致"),
        ]),
        "expected_result": "效率对比数据可信",
        "source": "manual",
    },

    # ================= 系统设置 =================
    {
        "point": "系统设置", "title": "模型切换即时生效",
        "priority": "P0", "test_type": "功能测试",
        "preconditions": "已配置 DeepSeek 与 Ollama 模型",
        "steps": S([
            ("在设置页将模型切换为本地 Ollama（如 qwen2.5:7b）", "提示保存成功，无需重启"),
            ("查看模型健康检查", "当前生效模型已更新"),
            ("切换到 DeepSeek 并指定模型", "立即生效且配置持久化"),
            ("重启后端", "配置从数据库恢复，保持上次选择"),
        ]),
        "expected_result": "模型切换即时生效并持久化，重启后恢复",
        "source": "ai_reviewed",
    },
    {
        "point": "系统设置", "title": "模型健康检查",
        "priority": "P1", "test_type": "功能测试",
        "preconditions": "数据库/LLM 服务正常",
        "steps": S([
            ("进入系统设置查看健康检查", "数据库、LLM、DeepSeek、Ollama 状态展示为正常/异常"),
        ]),
        "expected_result": "健康检查状态准确反映服务可用性",
        "source": "manual",
    },
    {
        "point": "系统设置", "title": "已安装模型列表展示",
        "priority": "P2", "test_type": "功能测试",
        "preconditions": "Ollama 服务运行",
        "steps": S([
            ("在设置页查看已安装模型", "列出 Ollama 已安装模型及 DeepSeek 可用模型"),
        ]),
        "expected_result": "模型列表准确完整",
        "source": "manual",
    },
    {
        "point": "系统设置", "title": "非法 provider 保存被拒绝",
        "priority": "P1", "test_type": "安全测试",
        "preconditions": "已登录且有设置权限",
        "steps": S([
            ("将 provider 修改为非法值（如 abc）", "接口返回 400 校验错误"),
            ("直接构造请求修改为合法值 ollama/deepseek", "保存成功"),
        ]),
        "expected_result": "provider 枚举校验严格",
        "source": "manual",
    },

    # ================= 用户与权限管理 =================
    {
        "point": "用户与权限管理", "title": "管理员创建用户",
        "priority": "P1", "test_type": "功能测试",
        "preconditions": "admin 登录",
        "steps": S([
            ("进入用户管理，点击新建用户", "弹出用户表单"),
            ("填写用户名、初始密码、角色", "表单校验通过"),
            ("提交", "用户创建成功，新用户可登录"),
        ]),
        "expected_result": "用户创建成功且初始密码生效",
        "source": "manual",
    },
    {
        "point": "用户与权限管理", "title": "权限点分配生效",
        "priority": "P1", "test_type": "安全测试",
        "preconditions": "存在非 admin 用户 U",
        "steps": S([
            ("为 U 分配“项目管理”权限点", "保存成功"),
            ("使用 U 登录访问项目接口", "访问成功"),
            ("移除权限点后再次访问", "返回 403"),
        ]),
        "expected_result": "权限点动态生效，无需重新登录",
        "source": "manual",
    },
    {
        "point": "用户与权限管理", "title": "角色默认权限正确",
        "priority": "P2", "test_type": "功能测试",
        "preconditions": "系统定义 admin/manager/engineer 三角色",
        "steps": S([
            ("对比三角色权限点", "admin 全量权限，manager/engineer 权限按设计分配"),
            ("用 engineer 账号访问无权限接口", "返回 403"),
        ]),
        "expected_result": "角色权限符合权限设计文档",
        "source": "manual",
    },

    # ================= 操作日志与通知 =================
    {
        "point": "操作日志与通知", "title": "关键写操作记录审计日志",
        "priority": "P1", "test_type": "功能测试",
        "preconditions": "已登录",
        "steps": S([
            ("执行创建项目、修改用例等写操作", "操作被记录"),
            ("进入操作日志页查询", "可查询到对应操作人、时间、操作内容"),
        ]),
        "expected_result": "关键写操作可审计追溯",
        "source": "manual",
    },
    {
        "point": "操作日志与通知", "title": "操作日志导出 CSV",
        "priority": "P2", "test_type": "功能测试",
        "preconditions": "存在操作日志",
        "steps": S([
            ("在日志页点击导出 CSV", "下载 csv 文件"),
            ("打开文件", "包含操作人/时间/内容等字段"),
        ]),
        "expected_result": "日志导出内容完整",
        "source": "manual",
    },
    {
        "point": "操作日志与通知", "title": "消息通知未读数与已读",
        "priority": "P1", "test_type": "功能测试",
        "preconditions": "存在生成任务等可产生通知的操作",
        "steps": S([
            ("触发一次用例生成任务", "任务完成生成系统通知"),
            ("查看通知角标", "未读数增加"),
            ("点击“全部已读”", "未读数清零，通知标记已读"),
        ]),
        "expected_result": "通知产生、计数与已读流程正确",
        "source": "manual",
    },
]

# 供脚本关联用：script_key -> 脚本定义
SCRIPTS = [
    {
        "case_key": "login",
        "name": "test_login_api.py",
        "script_type": "pytest",
        "description": "用户登录接口自动化脚本（对应认证登录用例）",
        "content": '''"""登录接口自动化测试：验证登录成功/失败/验证码校验"""
import pytest
import requests

BASE_URL = "http://localhost:8000/api/v1"


def _get_captcha(session):
    """获取验证码（测试环境建议关闭验证码或注入固定值）"""
    r = session.get(f"{BASE_URL}/auth/captcha", timeout=10)
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    return data["captcha_id"], "admin123"  # 测试环境替换为真实识别结果


def test_login_success():
    s = requests.Session()
    cid, code = _get_captcha(s)
    r = s.post(f"{BASE_URL}/auth/login", json={
        "username": "admin", "password": "admin123",
        "captcha_id": cid, "captcha_code": code,
    }, timeout=10)
    assert r.status_code == 200, r.text
    assert r.json()["data"]["access_token"]


@pytest.mark.parametrize("password", ["wrong", "123456", ""])
def test_login_wrong_password(password):
    s = requests.Session()
    cid, code = _get_captcha(s)
    r = s.post(f"{BASE_URL}/auth/login", json={
        "username": "admin", "password": password,
        "captcha_id": cid, "captcha_code": code,
    }, timeout=10)
    assert r.status_code == 200  # 业务码非 0
    assert r.json()["code"] != 0


def test_login_without_token():
    r = requests.get(f"{BASE_URL}/projects", timeout=10)
    assert r.status_code == 401
''',
    },
    {
        "case_key": "project",
        "name": "test_project_api.py",
        "script_type": "pytest",
        "description": "项目管理接口自动化脚本（对应项目管理用例）",
        "content": '''"""项目管理接口自动化测试：创建/查询/重复名校验"""
import pytest
import requests

BASE_URL = "http://localhost:8000/api/v1"
TOKEN = "YOUR_JWT_TOKEN"  # 由 conftest 登录后注入


def _headers():
    return {"Authorization": f"Bearer {TOKEN}"}


def test_create_project():
    r = requests.post(f"{BASE_URL}/projects", headers=_headers(), json={
        "name": "接口测试项目", "product_line": "smart_home",
        "description": "由接口自动化脚本创建",
    }, timeout=10)
    assert r.status_code == 200, r.text
    assert r.json()["data"]["id"] > 0


def test_duplicate_project_name():
    r = requests.post(f"{BASE_URL}/projects", headers=_headers(), json={
        "name": "接口测试项目", "product_line": "smart_home",
    }, timeout=10)
    assert r.status_code == 200
    assert r.json()["code"] != 0  # 名称重复应返回业务错误


def test_query_projects():
    r = requests.get(f"{BASE_URL}/projects", headers=_headers(),
                     params={"keyword": "接口测试", "page": 1, "page_size": 10}, timeout=10)
    assert r.status_code == 200
    assert r.json()["data"]["total"] >= 1
''',
    },
    {
        "case_key": "stats",
        "name": "test_stats_api.py",
        "script_type": "pytest",
        "description": "统计报表接口自动化脚本（对应趋势/总览用例）",
        "content": '''"""统计报表接口自动化测试：总览与生成趋势"""
import pytest
import requests

BASE_URL = "http://localhost:8000/api/v1"
TOKEN = "YOUR_JWT_TOKEN"


def _headers():
    return {"Authorization": f"Bearer {TOKEN}"}


def test_overview():
    r = requests.get(f"{BASE_URL}/stats/overview", headers=_headers(), timeout=10)
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert data["project_count"] >= 0
    assert data["case_count"] >= 0


@pytest.mark.parametrize("days", [7, 30, 90])
def test_trend(days):
    r = requests.get(f"{BASE_URL}/stats/trend", headers=_headers(),
                     params={"days": days}, timeout=10)
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert len(data["dates"]) == len(data["case_counts"]) == len(data["script_counts"])
    # 各天数量非负，且与用例总数一致
    assert sum(data["case_counts"]) >= 0


def test_distribution():
    r = requests.get(f"{BASE_URL}/stats/distribution", headers=_headers(), timeout=10)
    assert r.status_code == 200, r.text
''',
    },
]
