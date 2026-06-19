"""快速 API 冒烟测试"""
import time
import urllib.request
import json
import sys

time.sleep(2)

results = []

def test(name, url, method="GET", body=None):
    try:
        if body is not None:
            data = json.dumps(body).encode("utf-8")
            req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"}, method=method)
        else:
            req = urllib.request.Request(url, method=method)
        resp = urllib.request.urlopen(req, timeout=30)
        resp_text = resp.read().decode("utf-8")
        if resp.status == 200:
            if resp_text.startswith("[") or resp_text.startswith("{"):
                parsed = json.loads(resp_text)
                results.append((name, True, str(parsed)[:200]))
                print(f"[PASS] {name} -> parsed JSON, length={len(resp_text)}")
            else:
                results.append((name, True, resp_text[:200]))
                print(f"[PASS] {name} -> text, length={len(resp_text)}")
        else:
            results.append((name, False, resp_text[:200]))
            print(f"[FAIL] {name} -> HTTP {resp.status}")
    except Exception as e:
        results.append((name, False, str(e)))
        print(f"[FAIL] {name} -> {type(e).__name__}: {str(e)[:200]}")

print("=" * 60)
print("Backend API 冒烟测试")
print("=" * 60)

test("health check", "http://127.0.0.1:8000/health")
test("documents list", "http://127.0.0.1:8000/api/documents")
test("document content", "http://127.0.0.1:8000/api/documents/content?path=/docs/cs/os-memory.md")
test("questions list", "http://127.0.0.1:8000/api/questions?file=/docs/cs/os-memory.md")

# Test submit
test(
    "test submit",
    "http://127.0.0.1:8000/api/test/submit",
    method="POST",
    body={
        "file_path": "/docs/cs/os-memory.md",
        "answers": [{"question_id": "test-1", "user_answer": "LRU"}]
    }
)

# Test copilot explain
test(
    "copilot explain",
    "http://127.0.0.1:8000/api/copilot/explain",
    method="POST",
    body={"selected_text": "Belady 异常", "file_path": "/docs/cs/os-memory.md", "headers": []}
)

# Test sessions
test("test sessions", "http://127.0.0.1:8000/api/test/sessions")

print()
print("=" * 60)
passed = sum(1 for _, ok, _ in results if ok)
total = len(results)
print(f"结果: {passed}/{total} 通过")
for name, ok, detail in results:
    status = "PASS" if ok else "FAIL"
    print(f"  [{status}] {name}")
    if not ok and detail:
        print(f"         {detail[:150]}")
