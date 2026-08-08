"""`docker stats` 的内存读数怎么解析。

**单独一个文件是因为它不需要 Docker**：`container_test.py` 整包被 `skipif` 挡在
「没有 docker 就跳过」后面，而解析纯粹是文本处理 —— 把它放进去等于在 CI 上永远不跑，
而这正是最该一直跑的部分：认错单位会让数字差 5%，且不会有任何一条报错指出来。
"""

from sandbox.container import parse_memory

# docker stats --format "{{.MemUsage}}" 的一行：斜杠后面是限额，不是占用
ONE_LINE = "1.5GiB / 2GiB"


def test_a_single_container_is_read_in_bytes() -> None:
    assert parse_memory(ONE_LINE) == int(1.5 * (1 << 30))


def test_the_limit_after_the_slash_is_not_counted() -> None:
    """按限额算等于把每个沙箱都当成吃满了 2g，那是容量推算里最贵的一个错。"""
    assert parse_memory("10MiB / 2GiB") == 10 * (1 << 20)


def test_several_containers_are_summed() -> None:
    assert parse_memory("1GiB / 2GiB\n1GiB / 2GiB\n") == 2 * (1 << 30)


def test_decimal_units_are_understood_too() -> None:
    """同一个字段在别的 docker 版本上出现过十进制单位。认错一套差 5%。"""
    assert parse_memory("1MB / 2GB") == 1_000_000


def test_an_idle_container_reads_zero() -> None:
    assert parse_memory("0B / 2GiB") == 0


def test_an_unreadable_line_counts_as_zero_instead_of_blowing_up() -> None:
    """一行认不出来不该让整次抓取失败 —— 那会连好的那几行一起丢掉。"""
    assert parse_memory("这不是内存\n2GiB / 4GiB") == 2 * (1 << 30)


def test_no_containers_reads_zero() -> None:
    assert parse_memory("") == 0
