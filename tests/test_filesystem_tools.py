"""
tests/test_filesystem_tools.py
本地文件系统工具（write_file / append_file）的 TDD 测试。

append_file 的设计动机：GLM 为超长 content 生成的工具参数 JSON 常因截断
或转义错误而解析失败，因此长文档必须分块写入——write_file 写首块，
append_file 逐块追加，每块保持在模型能稳定生成的长度量级。
"""

import asyncio

from learning_factory.tools.filesystem import FILESYSTEM_TOOL_SCHEMAS, append_file, read_file, write_file


def _run(coro):
    """同步执行异步工具函数（工具内部无真实网络等待，直接跑一次性事件循环）。"""
    return asyncio.run(coro)


def test_append_file_creates_when_missing(tmp_path, monkeypatch):
    """目标文件不存在时，append_file 等同于新建并写入（含父目录）。"""
    monkeypatch.chdir(tmp_path)
    result = _run(append_file(path="out/notes.md", content="第一块"))
    assert "[成功]" in result
    assert (tmp_path / "out" / "notes.md").read_text(encoding="utf-8") == "第一块"


def test_append_file_appends_to_existing(tmp_path, monkeypatch):
    """目标文件已存在时，append_file 在末尾追加，不覆盖已有内容。"""
    monkeypatch.chdir(tmp_path)
    _run(write_file(path="out/notes.md", content="第一块"))
    result = _run(append_file(path="out/notes.md", content="\n第二块"))
    assert "[成功]" in result
    assert (tmp_path / "out" / "notes.md").read_text(encoding="utf-8") == "第一块\n第二块"


def test_append_file_rejects_path_escape(tmp_path, monkeypatch):
    """路径穿越到工作目录之外时拒绝追加（与 write_file 安全策略一致）。"""
    monkeypatch.chdir(tmp_path)
    result = _run(append_file(path="../evil.txt", content="x"))
    assert "[错误]" in result
    assert "当前工作目录之外" in result


def test_append_file_registered_in_tool_registry():
    """append_file 必须已注册进 TOOL_REGISTRY，模型才能实际调用到它。"""
    from learning_factory.tools import TOOL_REGISTRY

    assert "append_file" in TOOL_REGISTRY


def test_write_file_rejects_oversized_chunk(tmp_path, monkeypatch):
    """write_file 硬上限：超过 1500 字符直接拒绝，不落盘，错误含分块引导。"""
    monkeypatch.chdir(tmp_path)
    result = _run(write_file(path="out/long.md", content="x" * 1501))
    assert "[错误]" in result
    assert "1500" in result
    assert "append_file" in result          # 引导改用追加分块
    assert not (tmp_path / "out" / "long.md").exists()  # 未落盘


def test_write_file_accepts_max_chunk(tmp_path, monkeypatch):
    """恰好 1500 字符（边界值）允许写入。"""
    monkeypatch.chdir(tmp_path)
    result = _run(write_file(path="out/edge.md", content="x" * 1500))
    assert "[成功]" in result
    assert (tmp_path / "out" / "edge.md").exists()


def test_append_file_rejects_oversized_chunk(tmp_path, monkeypatch):
    """append_file 硬上限：超过 1500 字符直接拒绝，错误引导拆小块。"""
    monkeypatch.chdir(tmp_path)
    _run(write_file(path="out/notes.md", content="首块"))
    result = _run(append_file(path="out/notes.md", content="y" * 1501))
    assert "[错误]" in result
    assert "1500" in result
    assert (tmp_path / "out" / "notes.md").read_text(encoding="utf-8") == "首块"  # 原文件未变


def test_append_file_accepts_max_chunk(tmp_path, monkeypatch):
    """恰好 1500 字符（边界值）允许追加。"""
    monkeypatch.chdir(tmp_path)
    _run(write_file(path="out/notes.md", content="首块"))
    result = _run(append_file(path="out/notes.md", content="y" * 1500))
    assert "[成功]" in result
    # "首块"为 2 个字符（len 按 Unicode 码点计数），故总长 = 2 + 1500
    assert len((tmp_path / "out" / "notes.md").read_text(encoding="utf-8")) == 2 + 1500


def test_schemas_mention_same_round_parallel_writes():
    """A：并行写入指示进入 schema——模型选工具/组参数时最贴近的决策点通道。"""
    by_name = {s["function"]["name"]: s["function"]["description"] for s in FILESYSTEM_TOOL_SCHEMAS}
    assert "同一轮并行" in by_name["write_file"]       # 不同文件的首块可同轮批量写
    assert "同一轮并行" in by_name["append_file"]      # 不同文件的追加块可同轮批量发
    assert "逐轮顺序追加" in by_name["append_file"]    # 同一文件的块必须串行（顺序敏感）


def test_read_file_returns_content_with_header(tmp_path, monkeypatch):
    """读取：内容 + 头部元信息（总行数/字符数/当前页范围）。"""
    monkeypatch.chdir(tmp_path)
    _run(write_file(path="docs/a.md", content="第一行\n第二行\n第三行"))
    result = _run(read_file(path="docs/a.md"))
    assert "第一行" in result and "第三行" in result
    assert "共 3 行" in result
    assert "docs/a.md" in result


def test_read_file_pagination(tmp_path, monkeypatch):
    """分页：默认 200 行封顶 + offset 续读提示；offset 续读取到剩余。"""
    monkeypatch.chdir(tmp_path)
    content = "\n".join(f"L{i}" for i in range(201))  # ~1206 字符，1500 写入上限内
    _run(write_file(path="big.txt", content=content))
    page1 = _run(read_file(path="big.txt"))
    assert "共 201 行" in page1
    assert "L0" in page1 and "L199" in page1
    assert "L200" not in page1                     # 最后一行在第二页
    assert "offset=200" in page1                   # 尾部续读提示
    page2 = _run(read_file(path="big.txt", offset=200))
    assert "L200" in page2


def test_read_file_missing_and_dir_errors(tmp_path, monkeypatch):
    """错误路径：文件不存在（引导 list_directory）；路径是目录。"""
    monkeypatch.chdir(tmp_path)
    missing = _run(read_file(path="nope.md"))
    assert "[错误]" in missing and "list_directory" in missing
    (tmp_path / "d").mkdir()
    isdir = _run(read_file(path="d"))
    assert "[错误]" in isdir


def test_read_file_registered_and_schema_pins_preread():
    """注册 + schema 决策点文案：续写前必读（防盲写覆盖）。"""
    from learning_factory.tools import TOOL_REGISTRY

    by_name = {s["function"]["name"]: s["function"]["description"] for s in FILESYSTEM_TOOL_SCHEMAS}
    assert "read_file" in TOOL_REGISTRY
    assert "必须先 read_file" in by_name["read_file"]   # 续写前先读既有内容
    assert "offset" in by_name["read_file"]             # 分页续读指引


def test_write_file_rejects_overwrite_existing_nonempty(tmp_path, monkeypatch):
    """防线：既有非空文件默认拒绝覆盖，内容不变，错误引导 append/read/显式覆盖。"""
    monkeypatch.chdir(tmp_path)
    _run(write_file(path="out/a.md", content="原有内容"))
    result = _run(write_file(path="out/a.md", content="新内容"))
    assert "[错误]" in result
    assert "已存在且非空" in result
    assert "append_file" in result and "overwrite=true" in result
    assert (tmp_path / "out" / "a.md").read_text(encoding="utf-8") == "原有内容"  # 原文未损


def test_write_file_explicit_overwrite(tmp_path, monkeypatch):
    """显式 overwrite=True 允许整体重写（正当重写需求的逃生门）。"""
    monkeypatch.chdir(tmp_path)
    _run(write_file(path="out/a.md", content="旧"))
    result = _run(write_file(path="out/a.md", content="新内容", overwrite=True))
    assert "[成功]" in result
    assert (tmp_path / "out" / "a.md").read_text(encoding="utf-8") == "新内容"


def test_write_file_empty_file_overwrite_allowed(tmp_path, monkeypatch):
    """空文件（0 字节）覆盖无信息损失，放行不设卡。"""
    monkeypatch.chdir(tmp_path)
    (tmp_path / "out").mkdir()
    (tmp_path / "out" / "empty.md").write_text("", encoding="utf-8")
    result = _run(write_file(path="out/empty.md", content="内容"))
    assert "[成功]" in result
    assert (tmp_path / "out" / "empty.md").read_text(encoding="utf-8") == "内容"


def test_write_schema_documents_overwrite_guard():
    """schema：overwrite 参数描述携带防线语义（模型决策点通道）。"""
    by_name = {s["function"]["name"]: s["function"] for s in FILESYSTEM_TOOL_SCHEMAS}
    props = by_name["write_file"]["parameters"]["properties"]
    assert "overwrite" in props
    assert "覆盖" in props["overwrite"]["description"]


def test_write_file_string_overwrite_value_rejected(tmp_path, monkeypatch):
    """防线收紧：字符串 "false"/"true" 等非布尔真值不穿透，仍拒绝覆盖。"""
    monkeypatch.chdir(tmp_path)
    _run(write_file(path="out/a.md", content="原有内容"))
    result = _run(write_file(path="out/a.md", content="新内容", overwrite="false"))
    assert "[错误]" in result and "已存在且非空" in result
    assert (tmp_path / "out" / "a.md").read_text(encoding="utf-8") == "原有内容"


def test_append_file_rejects_empty_content(tmp_path, monkeypatch):
    """空内容追加拒绝：不落盘、不创建目录，错误引导带实内容重试。"""
    monkeypatch.chdir(tmp_path)
    result = _run(append_file(path="out/a.md", content=""))
    assert "[错误]" in result
    assert "空" in result
    assert not (tmp_path / "out").exists()  # 拒绝时不创建父目录/文件


def test_append_file_allows_newline_separator(tmp_path, monkeypatch):
    """守护：仅拒完全空串，换行分隔符追加（合法用途）放行。"""
    monkeypatch.chdir(tmp_path)
    _run(write_file(path="out/a.md", content="第一段"))
    result = _run(append_file(path="out/a.md", content="\n"))
    assert "[成功]" in result
    assert (tmp_path / "out" / "a.md").read_text(encoding="utf-8") == "第一段\n"
