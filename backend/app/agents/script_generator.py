"""测试脚本生成智能体: 将测试用例转换为可执行的自动化测试脚本

支持六种脚本类型:
- pytest:  单元测试脚本（mock 硬件交互）
- api:     接口自动化脚本（requests + pytest）
- ui:      UI 自动化脚本（playwright + pytest）
- android: 安卓 APP 自动化脚本（Appium + uiautomator2）
- ios:     iOS APP 自动化脚本（Appium + XCUITest）
- custom:  自定义脚本（用户补充要求）

生成采用文本模式（非 json mode），要求模型只输出代码。
"""
from app.agents.base import BaseAgent

SCRIPT_TYPE_META = {
    "pytest": {
        "label": "单元测试脚本",
        "framework": "pytest + pytest-mock",
        "requirement": (
            "使用 pytest 框架 + Python 3；"
            "针对嵌入式场景使用 mock/pytest-mock 模拟硬件交互（如串口 UART、GPIO、按键、显示屏、网络通信等）；"
            "每个测试用例对应一个 test_ 开头的测试函数，使用 fixture 组织前置条件与清理。"
        ),
    },
    "api": {
        "label": "接口自动化脚本",
        "framework": "pytest + requests",
        "requirement": (
            "使用 pytest + requests 实现接口自动化；"
            "将用例的步骤映射为 HTTP 请求（方法、URL、请求头、请求体），预期结果映射为状态码与响应体断言；"
            "使用 fixture 提供 base_url 与会话（session），支持超时与错误处理。"
        ),
    },
    "ui": {
        "label": "UI 自动化脚本",
        "framework": "pytest + playwright",
        "requirement": (
            "使用 pytest + playwright 实现 UI 自动化；"
            "将用例步骤映射为页面操作（点击、输入、导航、断言元素可见/文本）；"
            "使用 page fixture，启动时设置 headless 与超时。"
        ),
    },
    "android": {
        "label": "安卓APP自动化脚本",
        "framework": "pytest + Appium (uiautomator2)",
        "is_mobile": True,
        "requirement": (
            "使用 pytest + Appium Python 客户端（appium-python-client）实现安卓 APP UI 自动化，底层由 uiautomator2 驱动；"
            "通过 adb 连接真机或模拟器，测试前检查设备连接状态；"
            "将用例步骤映射为控件查找（优先 resource-id，其次 text / content-desc）、点击、输入、滑动、返回等操作与元素断言；"
            "使用 fixture 统一初始化 Appium driver 与 desired capabilities（platformName=Android、platformVersion、deviceName/udid、appPackage、appActivity、noReset 等），并在 teardown 中退出 driver；"
            "被测包名与启动 Activity 未知时在代码中以常量占位并注释说明需要替换。"
        ),
    },
    "ios": {
        "label": "iOS APP自动化脚本",
        "framework": "pytest + Appium (XCUITest)",
        "is_mobile": True,
        "requirement": (
            "使用 pytest + Appium Python 客户端（appium-python-client）实现 iOS APP UI 自动化，automationName 使用 XCUITest；"
            "连接真机或模拟器（XCUITest 驱动），测试前检查设备连接状态；"
            "将用例步骤映射为控件查找（优先 accessibility id，其次 label / name）、点击、输入、滑动、返回等操作与元素断言；"
            "使用 fixture 统一初始化 Appium driver 与 desired capabilities（platformName=iOS、platformVersion、deviceName/udid、bundleId、automationName=XCUITest、noReset 等），并在 teardown 中退出 driver；"
            "被测 bundleId 未知时在代码中以常量占位并注释说明需要替换。"
        ),
    },
    "custom": {
        "label": "自定义脚本",
        "framework": "pytest",
        "requirement": (
            "根据用户补充要求生成自定义自动化测试脚本；"
            "若用户未提供具体要求，则默认按 pytest 单元测试生成。"
        ),
    },
}

SCRIPT_GENERATE_PROMPT = """你是一名资深嵌入式测试开发工程师，擅长把测试用例自动转换为可直接运行的自动化测试脚本。

请根据以下【测试用例】生成一份 {label}。

【脚本类型与要求】
- 类型: {label}
- 框架: {framework}
- 技术要求: {requirement}
- 语言: Python 3

【附加要求】
{custom_prompt}

【测试用例】
{cases}

【输出要求】
1. 只输出完整的 Python 源代码，不要输出任何解释文字、不要使用 markdown 代码块包裹
2. 脚本必须包含必要的 import、常量、fixture 与测试函数，保证可被 pytest 直接收集运行
3. 每个测试用例对应一个独立的 test_ 函数，函数名体现用例要点
4. 用例的前置条件映射为 fixture 或函数内初始化，测试步骤映射为操作代码，预期结果映射为断言
5. 添加必要的注释说明每个测试步骤对应用例中的哪一步
6. {hardware_note}
"""


class ScriptGeneratorAgent(BaseAgent):
    name = "script_generator"
    system_prompt = "你是一名资深的嵌入式测试开发工程师，擅长 Python 自动化测试脚本编写。"

    def run(
        self,
        cases: list[dict],
        script_type: str = "pytest",
        custom_prompt: str = "",
        template: dict | None = None,
    ) -> dict:
        """根据用例列表生成测试脚本，返回 {content, framework, language, description}

        template: FR-6.4 自定义模板，{name, framework, template_content, description}
        """
        script_type = script_type if script_type in SCRIPT_TYPE_META else "pytest"
        meta = SCRIPT_TYPE_META[script_type]

        # 移动端（android/ios）脚本必须连接真实设备/模拟器，硬件说明与 mock 类类型不同
        if meta.get("is_mobile"):
            hardware_note = (
                "脚本面向真实设备/模拟器执行：使用 fixture 检查设备连接状态（如 adb devices / Appium 连接），"
                "设备未就绪时给出清晰提示；在脚本头部注释明确环境依赖（adb、Appium 版本、"
                "desired capabilities 中的包名/Activity 或 bundleId 等），不得用 mock 替代真实驱动"
            )
        else:
            hardware_note = "对依赖真实硬件/外部服务的部分使用 mock 或注入方式处理，保证脚本可独立运行"

        cases_text = self._format_cases(cases)
        custom = f"- {custom_prompt}" if custom_prompt else "- 无"
        prompt = (
            SCRIPT_GENERATE_PROMPT.replace("{label}", meta["label"])
            .replace("{framework}", meta["framework"])
            .replace("{requirement}", meta["requirement"])
            .replace("{hardware_note}", hardware_note)
            .replace("{custom_prompt}", custom)
            .replace("{cases}", cases_text)
        )
        if template and template.get("template_content"):
            template_block = (
                "【自定义模板参考】（请严格遵守）\n"
                f"- 模板名称: {template.get('name', '')}\n"
                f"- 模板说明: {template.get('description') or '无'}\n"
                f"- 模板框架: {template.get('framework') or '无'}\n"
                "请以模板代码为基础骨架生成脚本：保留模板中可复用的 import、常量、fixture、辅助函数与固定结构，"
                "将测试用例映射到模板预留的业务位置；模板中不可复用的示例代码应替换为对应用例的实现，"
                "并保持整体风格与模板一致。\n"
                f"【模板代码】\n{template['template_content']}"
            )
            prompt = prompt + "\n\n" + template_block
        content = self._call(prompt)
        framework = (template or {}).get("framework") or meta["framework"]
        title = f"{meta['label']}_{self._build_title(cases)}"
        return {
            "content": content,
            "framework": framework,
            "language": "python",
            "description": f"由 {len(cases)} 条测试用例自动生成的{meta['label']}"
            + (f"（模板: {template.get('name', '')}）" if template else ""),
            "suggest_name": title,
        }

    def _call(self, prompt: str) -> str:
        """调用 LLM 生成代码，清洗代码块标记"""
        content = self.llm.chat(prompt, system=self.system_prompt, temperature=0.3)
        content = content.strip()
        # 兼容模型输出 markdown 代码块的情况
        if content.startswith("```"):
            lines = content.splitlines()
            if lines and lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            content = "\n".join(lines)
        return content.strip()

    @staticmethod
    def _format_cases(cases: list[dict]) -> str:
        """将用例格式化为模型易读的文本"""
        blocks = []
        for i, c in enumerate(cases, 1):
            title = c.get("title") or "未命名用例"
            pre = c.get("preconditions") or "无"
            expected = c.get("expected_result") or "无"
            steps = c.get("steps") or []
            step_lines = []
            for s in steps:
                no = s.get("step_no", "")
                action = s.get("action", "")
                exp = s.get("expected", "")
                step_lines.append(f"    {no}. {action}  ->  预期: {exp}")
            steps_text = "\n".join(step_lines) if step_lines else "    （无具体步骤）"
            blocks.append(
                f"用例 {i}: {title}\n"
                f"  用例等级: {c.get('priority', '-')} | 类型: {c.get('test_type', '-')}\n"
                f"  前置条件: {pre}\n"
                f"  测试步骤:\n{steps_text}\n"
                f"  预期结果: {expected}"
            )
        return "\n\n".join(blocks)

    @staticmethod
    def _build_title(cases: list[dict]) -> str:
        """基于用例标题构建脚本文件名（取第一个用例标题前 20 字符）"""
        first = ""
        for c in cases:
            t = (c.get("title") or "").strip()
            if t:
                first = t
                break
        first = "".join(ch for ch in first if ch not in '\\/:*?"<>|')
        return first[:20] or "test_script"
