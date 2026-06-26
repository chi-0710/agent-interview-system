"""
代码执行引擎 - 防幻觉沙箱

核心思路：
- 用物理执行验证代码正确性，而非纯 LLM 语义评判
- LLM 只做"助教"：基于确定的执行结果生成错因解释
- 支持两种执行模式：subprocess（本地快速）和 Docker（隔离沙箱）

输出格式：
{
    "passed": bool,
    "total_tests": int,
    "pass_count": int,
    "stdout": str,
    "stderr": str,
    "execution_time_ms": float,
    "test_results": [{"name": str, "passed": bool, "input": str, "expected": str, "actual": str}, ...]
    "error": str | None
}
"""
import json
import logging
import os
import subprocess
import tempfile
import time
from typing import List, Optional

logger = logging.getLogger(__name__)


class CodeExecutionResult:
    """代码执行结果"""

    def __init__(self):
        self.passed: bool = False
        self.total_tests: int = 0
        self.pass_count: int = 0
        self.stdout: str = ""
        self.stderr: str = ""
        self.execution_time_ms: float = 0.0
        self.test_results: List[dict] = []
        self.error: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "total_tests": self.total_tests,
            "pass_count": self.pass_count,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "execution_time_ms": self.execution_time_ms,
            "test_results": self.test_results,
            "error": self.error,
        }


def _run_subprocess_python(
    code: str,
    test_cases: List[dict],
    timeout: float = 5.0,
) -> CodeExecutionResult:
    """
    通过 subprocess 执行 Python 代码（本地快速模式）。

    test_cases 格式：
    [{"name": "测试1", "input": {"a: 1, "b": 2}, "expected": 3, "function": "add"}]

    注入方式：在用户代码后追加测试代码，通过 print(JSON) 输出结果
    """
    result = CodeExecutionResult()
    result.total_tests = len(test_cases)

    # 构建测试脚手架
    test_code_lines = []
    test_code_lines.append("import json")
    test_code_lines.append("")
    test_code_lines.append("# ===== 用户代码 =====")
    test_code_lines.append(code)
    test_code_lines.append("")
    test_code_lines.append("# ===== 测试用例 =====")
    test_code_lines.append("results = []")

    for i, tc in enumerate(test_cases):
        func_name = tc.get("function", "solution")
        test_input = tc.get("input", {})
        expected = tc.get("expected", None)
        test_name = tc.get("name", f"test_{i+1}")

        # 构造调用参数字符串
        args_str = ", ".join([f"{k}={repr(v)}" for k, v in test_input.items()])

        test_code_lines.append(f"try:")
        test_code_lines.append(f"    _actual = {func_name}({args_str})")
        test_code_lines.append(f"    _passed = _actual == {repr(expected)}")
        test_code_lines.append(f"    results.append({{")
        test_code_lines.append(f"        'name': {repr(test_name)},")
        test_code_lines.append(f"        'passed': _passed,")
        test_code_lines.append(f"        'input': {repr(json.dumps(test_input, ensure_ascii=False))},")
        test_code_lines.append(f"        'expected': {repr(str(expected))},")
        test_code_lines.append(f"        'actual': repr(_actual) if _actual is not None else 'None',")
        test_code_lines.append(f"    }})")
        test_code_lines.append(f"except Exception as e:")
        test_code_lines.append(f"    results.append({{")
        test_code_lines.append(f"        'name': {repr(test_name)},")
        test_code_lines.append(f"        'passed': False,")
        test_code_lines.append(f"        'input': {repr(json.dumps(test_input, ensure_ascii=False))},")
        test_code_lines.append(f"        'expected': {repr(str(expected))},")
        test_code_lines.append(f"        'actual': f'Error: {{str(e)[:200]}}',")
        test_code_lines.append(f"    }})")

    test_code_lines.append("")
    test_code_lines.append("print(json.dumps(results, ensure_ascii=False))")

    full_code = "\n".join(test_code_lines)

    # 写入临时文件执行
    tmp_file = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False, encoding="utf-8"
        ) as f:
            f.write(full_code)
            tmp_file = f.name

        start_time = time.time()
        proc = subprocess.run(
            ["python", tmp_file],
            capture_output=True,
            text=True,
            timeout=timeout,
            encoding="utf-8",
            errors="replace",
        )
        result.execution_time_ms = (time.time() - start_time) * 1000
        result.stdout = proc.stdout
        result.stderr = proc.stderr

        # 解析测试结果
        try:
            output_lines = proc.stdout.strip().split("\n")
            last_line = output_lines[-1] if output_lines else ""
            test_results = json.loads(last_line)
            if isinstance(test_results, list):
                result.test_results = test_results
                result.pass_count = sum(1 for r in test_results if r.get("passed"))
                result.passed = result.pass_count == result.total_tests
        except (json.JSONDecodeError, IndexError):
            # 解析失败，说明代码可能有语法错误
            result.passed = False
            result.pass_count = 0
            if proc.stderr:
                result.error = proc.stderr[:500]

    except subprocess.TimeoutExpired:
        result.error = f"执行超时（{timeout}s）"
        result.passed = False
        result.execution_time_ms = timeout * 1000
    except Exception as e:
        result.error = f"执行异常：{str(e)}"
        result.passed = False
    finally:
        if tmp_file and os.path.exists(tmp_file):
            try:
                os.unlink(tmp_file)
            except OSError:
                pass

    return result


def execute_code(
    code: str,
    language: str = "python",
    test_cases: List[dict] = None,
    use_docker: bool = False,
    timeout: float = 5.0,
) -> dict:
    """
    执行代码并返回执行结果。

    Args:
        code: 用户提交的代码
        language: 编程语言（目前支持 python）
        test_cases: 测试用例列表
        use_docker: 是否使用 Docker 沙箱（默认关闭，用 subprocess 快速模式）
        timeout: 超时时间（秒）

    Returns:
        CodeExecutionResult.to_dict()
    """
    if not test_cases:
        test_cases = []

    if language != "python":
        result = CodeExecutionResult()
        result.error = f"暂不支持的语言: {language}，仅支持 python"
        return result.to_dict()

    if use_docker:
        # TODO: Docker 沙箱模式
        # 预留接口，当前回退到 subprocess
        logger.info("[code_exec] docker 模式暂未实现，回退到 subprocess")

    result = _run_subprocess_python(code, test_cases, timeout=timeout)
    logger.info(
        f"[code_exec] result: passed={result.passed}, "
        f"{result.pass_count}/{result.total_tests}, "
        f"time={result.execution_time_ms:.0f}ms"
    )
    return result.to_dict()


def get_test_cases_for_question(question_id: str) -> List[dict]:
    """
    根据题目 ID 获取预设的测试用例。

    目前使用内置映射，后续可从数据库读取。
    """
    # 内置测试用例映射（示例）
    TEST_CASE_MAP = {
        "q-os-3": [
            {
                "name": "基本用例1：指针扫过访问位为1的页面",
                "function": "clock_algorithm_step",
                "input": {"ref_bits": [1, 0, 1], "pointer": 0},
                "expected": (0, 0),
            },
            {
                "name": "基本用例2：遇到访问位为0的页面",
                "function": "clock_algorithm_step",
                "input": {"ref_bits": [1, 0, 1], "pointer": 1},
                "expected": (1, 0),
            },
        ],
    }
    return TEST_CASE_MAP.get(question_id, [])